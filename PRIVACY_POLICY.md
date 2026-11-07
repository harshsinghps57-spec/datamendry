# DataMendry Privacy Policy

**Effective date:** 7 November 2026  
**Website:** https://datamendry-demo.onrender.com/  
**Privacy contact:** skylar.hs0106@gmail.com

**Public beta:** DataMendry is intended for nonsensitive CSV files. It is not independently security-audited.

## 1. Who we are

DataMendry is an independently operated, open-source, public-beta web application that helps people inspect, clean, analyze, and export CSV data. This notice describes the practices of the DataMendry website at https://datamendry-demo.onrender.com/. It does not cover independently hosted copies of the open-source project.

For privacy questions and account-deletion requests, contact skylar.hs0106@gmail.com.

## 2. Information we process

Account information: When you sign in, we process the account identifier and email address supplied by Supabase Auth. Google sign-in may also supply your basic Google profile information (such as your display name or profile image) if made available through the sign-in process. We use this information to authenticate you and associate your saved files with your account.

CSV files and analysis results: DataMendry processes the CSV files you choose to upload, their filenames, and data-derived summaries, previews, cleaning rules, and exported results. A CSV may contain personal information that you put in it; please do not upload sensitive, confidential, regulated, or real-world personal datasets to this public beta.

Technical and usage information: The hosting and authentication providers may process connection details, device/browser information, IP addresses, requests, errors, timestamps, and security logs to operate and protect the service. The website also includes a Cloudflare Web Analytics beacon that measures website usage.

## 3. Google sign-in and email authentication

Google Sign-In is used to verify your identity and enable your DataMendry account through Supabase Auth. DataMendry does not ask for access to your Gmail inbox, Google Drive, or other Google files through this basic sign-in flow, and does not receive your Google password.

Existing email/password accounts, invitation links, confirmation messages, and password recovery are handled through Supabase Auth. DataMendry uses configured email delivery (currently Gmail SMTP) to send relevant authentication messages. Passwords and authentication verification are managed by the authentication provider rather than stored by DataMendry in its CSV-processing database.

Session tokens for signed-in accounts are held in the browser tab session storage for the session. A separate, temporary browser session cookie is used to associate guest analysis workspaces with the browser.

## 4. CSV uploads, cloud storage, and processing

Guest and analysis uploads are processed on the DataMendry application server. The public deployment uses temporary, disk-backed processing workspaces and currently configures a roughly one-hour workspace lifetime; cleanup is not instantaneous, and temporary workspaces may disappear earlier if the hosting instance restarts.

When a signed-in user chooses to save an original CSV, DataMendry stores it in a private Supabase Storage bucket under that user’s account-specific folder. The app uses user-scoped access policies to limit which stored files a signed-in user can list, read, upload, and delete. DataMendry does not silently overwrite your saved original when you preview a proposed cleanup or download a transformed copy.

File size, usage, and storage quotas apply. Temporary analysis data and saved cloud originals have different retention behavior. The public beta is not a backup service; keep your own copies.

## 5. Why we use information

We use information to sign users in, maintain account sessions, import and analyze CSV data, show reports, preview changes, produce user-requested exports, store and retrieve originals that users elect to save, prevent abuse, troubleshoot failures, and maintain the service. We do not use Google sign-in information to access unrelated Google services.

We do not intentionally sell your uploaded CSV content or account information. We do not use CSV contents for advertising.

## 6. Service providers and optional AI

DataMendry relies on Supabase for accounts and optional saved-original storage, Google for Google Sign-In, Render for hosting and temporary CSV processing, Gmail SMTP for authentication email delivery, and Cloudflare Web Analytics for traffic measurement. These providers may process limited information needed to provide their services under their own terms and privacy notices.

The app includes an optional connected-AI control. If an external AI service is enabled in a future or configured deployment, the interface requests your consent before sending your instruction and relevant column names. Do not enter personal, confidential, or sensitive information into assistant prompts. A connected service may have its own privacy terms; ordinary CSV repair features do not require a connected AI provider.

## 7. Retention and deletion

Guest processing copies on the current public Render deployment are generally configured to expire after about one hour and can also be lost when the instance restarts. Expiration is not immediate secure erasure; operational logs may have separate provider-defined retention periods.

You can use the Delete control in My Datasets to request deletion of an individual saved original from Supabase Storage, and the Delete uploaded data control to remove the current temporary analysis workspace. Deletion requests may not instantly remove all provider backups, caches, or operational logs.

To request access, correction, or deletion of your DataMendry account and associated personal information, email skylar.hs0106@gmail.com from the address associated with your account. We may need to verify account ownership before acting. Account deletion is not currently offered as an automated self-service feature.

## 8. Security

DataMendry uses HTTPS on the hosted website, signed-in sessions, temporary guest-session separation, and private-storage access policies. No website or storage system can promise absolute security, and this open-source public beta has not undergone an independent security audit. Do not use DataMendry to store or process sensitive, regulated, or confidential information.

## 9. Your choices

You can try the sample data or use temporary guest processing without signing in, decline Google Sign-In, choose whether to save a CSV original, delete saved files through My Datasets, and ask for account or personal-data deletion by email. You can also review or revoke DataMendry’s Google sign-in access from your Google Account settings.

## 10. Changes to this policy

We may update this notice as the service changes. The effective date below indicates the current version. Material changes should be reflected in the publicly accessible policy before new practices are introduced.

## 11. Contact

For privacy questions, data requests, or account-deletion requests, email skylar.hs0106@gmail.com. Do not send CSV contents, passwords, tokens, or other sensitive data in your support message.
