# Security Incident Response Procedure

Procedure ID: IR-007  
Owner: Security Operations  
Status: Current  
Effective date: 10 January 2026

## Reporting channels

Urgent security incidents must be reported through extension 7711 or `security-urgent@northstar.example`. General IT tickets are not monitored continuously and must not be used as the only channel for an active compromise, stolen device, malware event, or public data exposure.

The person reporting should preserve evidence, note the time, and avoid making uncoordinated changes. A suspected phishing email should not be deleted. A stolen device should not be remotely wiped by the user unless Security instructs them to do so.

## Severity levels and response targets

| Severity | Example | Acknowledgement target | Incident lead |
| --- | --- | --- | --- |
| P1 Critical | Active production breach, exposed Restricted data, ransomware | 10 minutes | Security Incident Commander |
| P2 High | Confirmed account takeover, stolen unlocked laptop | 30 minutes | Security on-call lead |
| P3 Medium | Contained malware, limited accidental disclosure | 4 business hours | Security analyst |
| P4 Low | Suspicious event with no evidence of compromise | 2 business days | Service desk or Security analyst |

Targets begin when the urgent report reaches Security. They are acknowledgement targets, not guaranteed resolution times.

## Initial response

The Security on-call analyst records the report, assigns a severity, opens an incident record, and preserves available evidence. For P1 and P2 incidents, the analyst starts an incident channel and assigns an incident lead. The incident lead coordinates containment, investigation, communication, and recovery.

Employees should disconnect a device from networks if they can do so safely, but should leave it powered on unless Security gives different instructions. They must not contact suspected attackers, notify customers, or post details publicly.

## Escalation

A P1 incident is escalated immediately to the Chief Information Security Officer, Chief Technology Officer, Legal, and Communications. Privacy is included when personal data may be involved. Customer notification is decided by Legal and the incident lead according to contractual and regulatory requirements.

## Closure and learning

P1 and P2 incidents require a written review. A P1 review must be completed within five working days after recovery; a P2 review must be completed within 10 working days. Reviews focus on causes, controls, and assigned actions rather than individual blame.
