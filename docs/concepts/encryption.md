# Encryption in This Project

The application stores highly sensitive information, including AAU portal credentials and academic records. To protect this information, all sensitive values are encrypted before they are persisted to the database.

The project currently uses **AES-256-GCM (Advanced Encryption Standard with Galois/Counter Mode)**, an authenticated encryption algorithm that provides both confidentiality and integrity.

Encryption is treated as an infrastructure concern and is accessed through the application's cipher port rather than being created directly inside application services.

---

# Security Goals

The encryption system is designed to satisfy the following goals:

* Prevent disclosure of stored passwords and grades if the database is compromised.
* Detect accidental or malicious modification of encrypted data.
* Allow application services to encrypt and decrypt data without depending on cryptographic implementation details.
* Minimize the amount of plaintext that exists in memory.
* Keep encryption centralized behind a single abstraction.

---

# Why AES-256-GCM

AES-256-GCM was selected because it provides **authenticated encryption with associated data (AEAD)**.

Unlike older encryption schemes that require separate encryption and integrity verification, AES-GCM performs both operations together.

This means encrypted data is:

* **Confidential** – attackers cannot recover the plaintext without the secret key.
* **Authenticated** – any modification to the ciphertext, nonce, or associated data causes decryption to fail.
* **Efficient** – GCM is designed for high performance and is widely accelerated by modern CPUs.

This significantly reduces the risk of accidentally implementing encryption correctly but authentication incorrectly.

---

# What Is AES?

AES (Advanced Encryption Standard) is a **symmetric-key block cipher** standardized by NIST and widely used throughout the industry.

Unlike asymmetric algorithms such as RSA, AES uses the **same secret key** for both encryption and decryption.

AES operates on fixed-size **128-bit blocks** regardless of key size.

Three standardized key lengths exist:

| Variant | Key Size | Typical Use                |
| ------- | -------- | -------------------------- |
| AES-128 | 128 bits | General-purpose encryption |
| AES-192 | 192 bits | Less commonly used         |
| AES-256 | 256 bits | High-security applications |

This project uses **AES-256**, providing the largest standardized key size.

---

# How AES Works (High Level)

Internally, AES repeatedly transforms each 128-bit block using a sequence of mathematical operations.

Each encryption round performs operations similar to:

1. Byte substitution
2. Row shifting
3. Column mixing
4. Round key addition

These transformations repeatedly scramble the plaintext until it becomes ciphertext.

AES-256 performs **14 rounds** of these transformations.

The exact mathematics are intentionally complex, but application developers rarely interact with these details directly because cryptographic libraries implement the algorithm securely.

---

# Why AES Needs a Mode of Operation

AES encrypts only one fixed-size block at a time.

Real application data is much larger than 128 bits, so AES must be combined with a **mode of operation** that defines how multiple blocks are processed.

Different modes provide different security properties.

---

# Common AES Modes

## AES-CBC (Cipher Block Chaining)

CBC was historically one of the most common AES modes.

Each block depends on the previous encrypted block, requiring a random initialization vector (IV).

Advantages:

* Simple and widely supported.
* Suitable for confidentiality.

Disadvantages:

* Does **not** provide integrity.
* Must be combined with a separate authentication algorithm such as HMAC.
* Incorrect implementations are vulnerable to padding oracle attacks.

Because confidentiality and integrity are separate concerns, CBC is more difficult to implement safely than modern authenticated modes.

---

## AES-GCM (Galois/Counter Mode)

This project currently uses AES-GCM.

Advantages:

* Provides confidentiality and authentication together.
* Detects tampering automatically.
* Supports Associated Authenticated Data (AAD).
* Fast on modern processors.
* Recommended for new applications.

Disadvantages:

* A nonce **must never** be reused with the same encryption key.

Because AES-GCM already authenticates every encrypted value, there is no need to maintain separate message authentication logic.

---

## AES-SIV (Synthetic Initialization Vector)

AES-SIV is another authenticated encryption mode designed to tolerate accidental nonce misuse.

Unlike GCM, AES-SIV remains secure even if a nonce is accidentally reused.

An important property of deterministic AES-SIV is that encrypting the same plaintext with the same key produces the same ciphertext.

This makes it possible to determine whether two encrypted values are identical without decrypting them.

Potential future applications include:

* detecting whether encrypted values have changed,
* performing encrypted equality comparisons,
* reducing unnecessary writes when encrypted data remains unchanged.

However, deterministic encryption also leaks equality information because identical plaintexts produce identical ciphertexts.

For sensitive application data such as passwords, grades, and assessment details, revealing equality relationships may not be desirable.

For this reason, the project currently favors randomized AES-GCM.

If future requirements include encrypted equality comparisons, AES-SIV may be evaluated carefully for specific use cases rather than replacing AES-GCM globally.

---

# Associated Authenticated Data (AAD)

AES-GCM allows callers to authenticate additional context that is **not encrypted**.

Associated data is included in the authentication calculation.

If the associated data changes, decryption fails even though it was never encrypted.

Typical examples include:

* user identifiers,
* resource identifiers,
* protocol versions,
* message types.

The application may supply associated data whenever integrity over contextual information is required.

---

# Service Structure

The `crypto/cipher.py` module exposes a small API to the rest of the application.

It provides:

* `AesGcmCipher` for encryption and decryption.
* `Ciphertext` as a storage-friendly encrypted token wrapper.
* `generate_key()` for generating a new Base64-encoded AES key.

Application services depend only on the cipher interface.

The concrete implementation is injected through the composition root, following the same dependency inversion principles used throughout the project.

---

# Storage Model

Every encryption operation follows the same lifecycle.

1. Generate a cryptographically secure random nonce.
2. Encrypt the plaintext using AES-256-GCM.
3. Produce the authentication tag.
4. Encode the resulting encrypted payload as a URL-safe Base64 token.
5. Persist the encrypted token.

Each encryption operation generates a new nonce, even if the plaintext has not changed.

Consequently, encrypting identical plaintext twice produces different ciphertext.

This property is intentional and improves confidentiality.

---

# How the Application Uses Encryption

Sensitive values are encrypted immediately before persistence.

Examples include:

* AAU portal passwords stored in `user_credentials`.
* Semester result payloads.
* Assessment details.
* Grade information.

Repositories persist only encrypted values.

Application services work with plaintext only for the minimum time required to perform business operations.

---

# Important Security Rules

The following rules are mandatory throughout the codebase.

* Never reuse a nonce with the same AES key.
* Never log plaintext passwords, decrypted grades, decrypted assessments, or encryption keys.
* Keep decrypted values in the smallest possible scope.
* Remove references to decrypted values immediately after use.
* Never implement custom cryptographic algorithms or modify cryptographic primitives.
* Always use the project's cipher abstraction instead of creating cryptographic objects directly within handlers or services.

---

# Future Considerations

The current implementation prioritizes strong confidentiality and authenticated encryption.

Future versions of the project may evaluate additional authenticated encryption modes such as AES-SIV if deterministic encryption or encrypted equality comparison becomes a genuine application requirement.

Any future migration would require careful evaluation of the information leaked by deterministic encryption and should be performed only for data where those trade-offs are acceptable.

Until then, AES-256-GCM remains the project's standard because it provides a strong balance of security, integrity, performance, and broad library support.
