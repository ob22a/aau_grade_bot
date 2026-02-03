import pytest
from portal.parser import PortalParser

SAMPLE_GRADE_REPORT = """
<table style="border: none !important;" class="table table-bordered table-striped table-hover"> <tbody><tr class="success"> <th align="left" style="width: 60px">No.</th> <th align="left">Course Title </th> <th align="left">Code</th> <th align="left">Credit&nbsp;Hour</th> <th align="left">ECTS</th> <th align="left">Grade </th> <th align="left">Assesment </th> </tr> <tr class="yrsm" style="background-color: transparent !important;"> <td colspan="7"> <br> <p style="color: #4682c0; font-weight: bold;">&nbsp;&nbsp;&nbsp; <span style="font-weight: bold"> Academic Year </span> : 2025/26, &nbsp;&nbsp;&nbsp; <span style="font-weight: bold"></span> Year III,&nbsp;&nbsp;&nbsp;<span style="font-weight: bold"> Semester </span> : One</p> <br> </td> </tr> <tr> <td> 1 </td> <td> Fundamental of Electrical circuits and Electronics- </td> <td> SECT-2121 </td> <td align="center"> 2.00 </td> <td align="center"> 5.00 </td> <td> A </td> <td> <button type="button" class="btn btn-default btn-sm" data-toggle="modal" data-target="#myModal" onclick="modalButtonClicked('ac5c7150-d851-4b85-adbc-5cd06a18b717','11111111-1111-1111-1111-111111111111','44e98d3c-fe3d-48b7-a13d-cb3334cda329')"> Assessment </button> </td> </tr> </tbody></table>
"""

SAMPLE_ASSESSMENT_DETAIL = """
<table class="table table-bordered table-striped table-hover">
    <tbody><tr class="text-primary"> <th colspan="3">Course : Fundamental of Electrical circuits and Electronics-</th></tr>
    <tr class="success">
        <th>S.No.</th>
        <th>Assessment </th>
        <th>Result</th>
    </tr>
        <tr>
            <td width="25px">1</td>
            <td>Individual Assignment ( 10% )</td>
            <td width="100px">9.5</td>
        </tr>
    <tr class="success">
        <th colspan="3" style="text-align: right;margin-right:15%">
                 Total Mark : 87 / 100
        </th>
    </tr>
</tbody></table>
"""

def test_parse_grade_report():
    parser = PortalParser()
    results = parser.parse_grade_report(SAMPLE_GRADE_REPORT)
    
    assert len(results) == 1
    assert results[0]["course_name"] == "Fundamental of Electrical circuits and Electronics-"
    assert results[0]["grade"] == "A"
    assert results[0]["assessment_ids"]["courseId"] == "44e98d3c-fe3d-48b7-a13d-cb3334cda329"
    assert results[0]["academic_year"] == "2025/26"

def test_parse_assessment_detail():
    parser = PortalParser()
    detail = parser.parse_assessment_detail(SAMPLE_ASSESSMENT_DETAIL)
    
    assert detail["course"] == "Fundamental of Electrical circuits and Electronics-"
    assert len(detail["grades"]) == 1
    assert detail["grades"][0]["name"] == "Individual Assignment"
    assert detail["grades"][0]["weight"] == "10%"
    assert detail["grades"][0]["result"] == "9.5"
    assert detail["totalMark"] == "87 / 100"
