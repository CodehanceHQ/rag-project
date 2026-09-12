# Data Classification and Retention Policy

Policy ID: DATA-008  
Owner: Data Governance  
Status: Current  
Effective date: 1 April 2026

## Classification levels

Northstar Analytics uses four information classifications: Public, Internal, Confidential, and Restricted.

Public information is approved for unrestricted external distribution. Internal information is routine business material intended for Northstar personnel and approved partners.

Confidential information could harm Northstar, a customer, or an individual if disclosed without authorization. Examples include contracts, non-public financial results, employee records, customer contact lists, and product roadmaps. It must be encrypted and shared only with people who have a business need.

Restricted information is Northstar's most sensitive information. Examples include authentication secrets, private encryption keys, production customer datasets, government identifiers, payment-card data, and unannounced acquisition plans. It requires explicitly approved access, a company-managed device, encryption, and storage in a system approved for Restricted data.

## Retention

Documents should not be retained indefinitely merely because storage is available. Contract records are retained for seven years after termination. Final financial records are retained for seven years after the end of the relevant financial year. Unsuccessful job-applicant records are retained for 12 months after the hiring decision. Routine operational logs are retained for 90 days unless they are subject to an investigation or legal hold.

A legal hold overrides the normal deletion schedule. Data covered by a legal hold must not be deleted or altered until Legal issues a written release.

## Sharing and disposal

Confidential and Restricted data must not be uploaded to an unapproved AI or retrieval system. Before a knowledge system is approved, its owner must document access control, deletion, audit logs, data location, backup handling, and the behavior of external model providers.

Paper containing Confidential or Restricted information must be placed in a locked destruction bin. Electronic media must be securely erased through the IT Asset team.

## Incident connection

Loss of a device containing Confidential or Restricted data must be reported under policy SEC-104. The reporter should tell Security the highest likely classification and the systems or files that may have been accessible. Security, not the reporter, determines final incident severity.
