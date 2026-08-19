"""Cron and cohort scan orchestration service."""
import json
import base64
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Any

from database.models import (
    CronRun, CohortState, CohortScan, User, UserCredential, 
    SystemSetting, SemesterResult, CronRunStatus, 
    CohortScanStatus, GradeChangeStatus, Semester
)
from crypto.cipher import Ciphertext
from parser.models import GradeReport
from repositories.sqlalchemy.unit_of_work import SqlAlchemyRepositoryUnitOfWork
from services.account_lifecycle.service import AccountLifecycleService
from sqlalchemy import select, and_, delete, func

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SchedulerRunResult:
    """Result of a single scheduler execution run."""
    started_at: datetime
    finished_at: datetime | None = None
    skipped: bool = False
    message: str = ""

class SchedulerService:
    """Manage atomic cron runs and cohort scan sequencing."""

    def __init__(
        self,
        lock: Any | None = None,
        notification_service: Any | None = None,
        portal_client: Any | None = None,
        session_factory: Any | None = None,
        cipher: Any | None = None,
    ) -> None:
        self.lock = lock
        self.notification_service = notification_service
        self.portal_client = portal_client
        self.session_factory = session_factory
        self.cipher = cipher

    def _parse_semester(self, label: str) -> Semester:
        lab = label.lower()
        if "2" in lab or "two" in lab or "second" in lab or " ii" in lab:
            return Semester.SECOND
        if "3" in lab or "three" in lab or "third" in lab or "iii" in lab:
            return Semester.THIRD
        return Semester.FIRST

    async def _detect_grade_diff(self, old_reports: list[GradeReport], new_reports: list[GradeReport]) -> list[str]:
        """Returns a list of course codes that have newly released grades."""
        old_grades = {}
        for rep in old_reports:
            for cg in rep.course_grades:
                if cg.grade and cg.grade.strip() and cg.grade.strip().upper() != "N/A":
                    old_grades[cg.course_code] = cg.grade

        new_released = []
        for rep in new_reports:
            for cg in rep.course_grades:
                if cg.grade and cg.grade.strip() and cg.grade.strip().upper() != "N/A":
                    if cg.course_code not in old_grades:
                        new_released.append(f"{cg.course_name} ({cg.course_code})")
        return new_released

    async def _scrape_user_and_detect(self, uow: SqlAlchemyRepositoryUnitOfWork, user: User, current_year: str, current_semester: Semester) -> list[str]:
        """Scrapes a user, updates DB, and returns a list of newly released subjects."""
        if not self.portal_client or not self.cipher:
            return []

        cred = await uow.session.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
        if not cred:
            return []
            
        try:
            password = self.cipher.decrypt(cred.encrypted_password)
            _profile, new_reports = await self.portal_client.scrape(user.university_id, password, user.university_id)
        except Exception as e:
            logger.warning(f"Scrape failed for user {user.telegram_id}: {e}")
            return []

        # Load old reports
        db_results = await uow.session.scalars(select(SemesterResult).where(SemesterResult.user_id == user.id))
        old_reports = []
        for res in db_results:
            try:
                old_reports.append(GradeReport.model_validate_json(self.cipher.decrypt(res.encrypted_result_detail)))
            except:
                pass

        new_released = await self._detect_grade_diff(old_reports, new_reports)

        # Save new reports back
        await uow.session.execute(delete(SemesterResult).where(SemesterResult.user_id == user.id))
        for rep in new_reports:
            rep_json = json.dumps(rep.model_dump())
            enc_rep = self.cipher.encrypt(rep_json)
            rep_payload = Ciphertext.from_token(enc_rep)
            rep_iv = base64.urlsafe_b64encode(rep_payload.nonce).decode("ascii")
            sr = SemesterResult(
                user_id=user.id,
                academic_year=rep.academic_year,
                semester=self._parse_semester(rep.semester_label),
                encrypted_result_detail=enc_rep,
                iv=rep_iv,
            )
            uow.session.add(sr)
        
        await uow.commit()
        return new_released

    async def run_once(self) -> SchedulerRunResult:
        """
        Executes a single pass of the background cron scheduler.
        
        This method will:
        1. Acquire a distributed lock to prevent concurrent cron executions.
        2. Clean up inactive user accounts (if enabled).
        3. Identify and update live cohorts based on the current academic term.
        4. Scrape the portal for a representative user of each cohort.
        5. If grades change for a cohort, trigger an exhaustive scrape for that cohort.
        6. Send targeted notifications to users who received grades, and informative broadcasts to those who did not.
        """
        started_at = datetime.now(timezone.utc)
        lock_key = "cron:run"
        if self.lock is not None:
            acquired = await self.lock.acquire(lock_key, ttl_seconds=3600)
            if not acquired:
                return SchedulerRunResult(
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    skipped=True,
                    message="Cron already running",
                )

        try:
            if not self.session_factory:
                return SchedulerRunResult(started_at=started_at, skipped=True, message="No DB")

            async with SqlAlchemyRepositoryUnitOfWork(self.session_factory) as uow:
                enabled_setting = await uow.session.scalar(select(SystemSetting).where(SystemSetting.key == "is_scheduling_enabled"))
                if not enabled_setting or enabled_setting.value.lower() != "true":
                    return SchedulerRunResult(started_at=started_at, skipped=True, message="Scheduling disabled")

                # Inactivity cleanup
                cleanup_enabled = await uow.session.scalar(select(SystemSetting).where(SystemSetting.key == "is_inactivity_cleanup_enabled"))
                if not cleanup_enabled or cleanup_enabled.value.lower() != "false":
                    lifecycle = AccountLifecycleService(notifier=self.notification_service, session_factory=self.session_factory)
                    await lifecycle.cleanup_inactive_users(60)

                curr_year_set = await uow.session.scalar(select(SystemSetting).where(SystemSetting.key == "current_academic_year"))
                curr_sem_set = await uow.session.scalar(select(SystemSetting).where(SystemSetting.key == "current_semester"))
                
                if not curr_year_set or not curr_sem_set:
                    return SchedulerRunResult(started_at=started_at, skipped=True, message="Current term not configured")
                    
                current_year = curr_year_set.value
                try:
                    current_semester = Semester[curr_sem_set.value.upper()]
                except KeyError:
                    current_semester = Semester.FIRST

                cron_run = CronRun(status=CronRunStatus.RUNNING)
                uow.session.add(cron_run)
                await uow.commit()

                # Sync Cohorts
                stmt = select(User.department_id, User.section).where(
                    and_(User.department_id.is_not(None), User.section.is_not(None), User.section != "none")
                ).distinct()
                active_groups = await uow.session.execute(stmt)
                for row in active_groups:
                    dept_id, section = row
                    state = await uow.session.scalar(
                        select(CohortState).where(
                            and_(
                                CohortState.department_id == dept_id,
                                CohortState.academic_year == current_year,
                                CohortState.semester == current_semester,
                                CohortState.section == section
                            )
                        )
                    )
                    if not state:
                        state = CohortState(
                            department_id=dept_id,
                            academic_year=current_year,
                            semester=current_semester,
                            section=section
                        )
                        uow.session.add(state)
                await uow.commit()

                # Find eligible cohorts
                two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
                eligible_states = await uow.session.scalars(
                    select(CohortState).where(
                        and_(
                            CohortState.academic_year == current_year,
                            CohortState.semester == current_semester,
                            (CohortState.last_probe_at == None) | (CohortState.last_probe_at < two_hours_ago)
                        )
                    )
                )

                cohorts_processed = 0
                for state in eligible_states.all():
                    rep_user = None
                    if state.representative_user_id:
                        rep_user = await uow.users.get_by_id(state.representative_user_id)
                    
                    if not rep_user or rep_user.department_id != state.department_id or rep_user.section != state.section:
                        rep_user = await uow.session.scalar(
                            select(User).where(
                                and_(User.department_id == state.department_id, User.section == state.section)
                            ).limit(1)
                        )
                        if rep_user:
                            state.representative_user_id = rep_user.id
                            await uow.commit()
                            
                    if not rep_user:
                        continue 

                    # Scrape Representative
                    scan = CohortScan(
                        run_id=cron_run.id,
                        department_id=state.department_id,
                        academic_year=state.academic_year,
                        semester=state.semester,
                        section=state.section,
                        representative_user_id=rep_user.id,
                        status=CohortScanStatus.IN_PROGRESS,
                        grade_change=GradeChangeStatus.NONE
                    )
                    uow.session.add(scan)
                    await uow.commit()

                    state.last_probe_at = datetime.now(timezone.utc)
                    await uow.commit()
                    
                    new_subjects = await self._scrape_user_and_detect(uow, rep_user, current_year, current_semester)
                    
                    if new_subjects:
                        scan.grade_change = GradeChangeStatus.DETECTED
                        state.last_grade_change_at = datetime.now(timezone.utc)
                        await uow.commit()
                        
                        # Full Cohort Scrape
                        cohort_users = await uow.session.scalars(
                            select(User).where(
                                and_(User.department_id == state.department_id, User.section == state.section)
                            )
                        )
                        cohort_users_list = cohort_users.all()
                        
                        users_who_got_it = set()
                        # Rep already scraped, and we know they got it
                        users_who_got_it.add(rep_user.telegram_id)
                        
                        if self.notification_service:
                            await self.notification_service.send_user(
                                rep_user.telegram_id,
                                f"🎉 <b>Grade Released!</b>\n\nYour grade for <b>{', '.join(new_subjects)}</b> has been released. Use /grades to check it."
                            )

                        for u in cohort_users_list:
                            if u.id == rep_user.id:
                                continue
                                
                            u_new_subjects = await self._scrape_user_and_detect(uow, u, current_year, current_semester)
                            if u_new_subjects:
                                users_who_got_it.add(u.telegram_id)
                                if self.notification_service:
                                    await self.notification_service.send_user(
                                        u.telegram_id,
                                        f"🎉 <b>Grade Released!</b>\n\nYour grade for <b>{', '.join(u_new_subjects)}</b> has been released. Use /grades to check it."
                                    )
                                    
                        total_users = len(cohort_users_list)
                        got_it_count = len(users_who_got_it)
                        
                        # Notify the ones who didn't get it
                        for u in cohort_users_list:
                            if u.telegram_id not in users_who_got_it:
                                if self.notification_service:
                                    await self.notification_service.send_user(
                                        u.telegram_id,
                                        f"⏳ <b>Grade Release Update</b>\n\n{got_it_count} out of {total_users} people in your cohort got a grade for <b>{', '.join(new_subjects)}</b>. Please wait patiently and check again later."
                                    )
                                    
                        # Cross-section broadcast
                        sibling_cohorts = await uow.session.scalars(
                            select(CohortState).where(
                                and_(
                                    CohortState.department_id == state.department_id,
                                    CohortState.academic_year == current_year,
                                    CohortState.semester == current_semester,
                                    CohortState.section != state.section
                                )
                            )
                        )
                        for sib in sibling_cohorts.all():
                            # Send broadcast to sib representative or all users? Plan said "broadcast to them"
                            sib_users = await uow.session.scalars(
                                select(User).where(
                                    and_(User.department_id == sib.department_id, User.section == sib.section)
                                )
                            )
                            for su in sib_users.all():
                                if self.notification_service:
                                    await self.notification_service.send_user(
                                        su.telegram_id,
                                        f"📢 <b>Department Update</b>\n\nA grade for <b>{', '.join(new_subjects)}</b> has been released for another section in your department. It might be released for you soon!"
                                    )
                                    
                    scan.status = CohortScanStatus.COMPLETED
                    await uow.commit()
                    cohorts_processed += 1

                cron_run.status = CronRunStatus.COMPLETED
                cron_run.finished_at = datetime.now(timezone.utc)
                await uow.commit()
                return SchedulerRunResult(started_at=started_at, finished_at=cron_run.finished_at, message=f"Processed {cohorts_processed} cohorts")

        finally:
            if self.lock is not None:
                await self.lock.release(lock_key)
