# Research and usability evidence

Complete these forms with real responses. Sample operational figures are fictional; these forms do not constitute research findings.

## Short planner interview or questionnaire

Explain the student project, ask whether the participant is willing to take part, and avoid collecting employee names or confidential operational records. Identify participants as P01, P02 and so on. Record the date and their general planning role only where needed.

1. How do you currently turn forecast workload into a staffing plan?
2. Which units do you use to measure workload?
3. What factors change the productive hours or productivity assumptions?
4. How do you account for absences?
5. Which shortages or deadline risks are hardest to identify?
6. How do you compare alternative staffing options?
7. Which reports help you review a plan?
8. What would make this prototype useful or difficult to use?

### Response record

Participant code: [ ]
Date: [ ]
Participation agreed: [ ]
Responses: [ ]
Key need or problem: [ ]
Requirement derived: [ ]
Evidence reference: [ ]

## Usability session

Use fictional data. Explain that the interface is being tested, not the participant. Avoid guiding them unless they become stuck; record any assistance.

| Task | Success condition | Time | Assistance | Feedback |
| --- | --- | --- | --- | --- |
| Find 8 October Day shift shortage | Identifies Picking 2 and Packing 1 | [ ] | [ ] | [ ] |
| Edit a workload plan | Saves intended forecast without duplicate | [ ] | [ ] | [ ] |
| Account for one absence | Understands scheduled minus absent staff | [ ] | [ ] | [ ] |
| Cover forecast in Scenarios | Gets 20 staff and zero volume shortfall | [ ] | [ ] | [ ] |
| Interpret deadline warning | Understands zero shortfall does not guarantee deadline | [ ] | [ ] | [ ] |
| Export a report | Selects range and obtains matching CSV | [ ] | [ ] | [ ] |

Participant code: [ ]
Date: [ ]
Most difficult task: [ ]
Suggested improvement: [ ]
Change implemented: [ ]
Retest outcome: [ ]

## Manual functional checks

- Run the automated tests first and keep the terminal output as dated evidence.
- Try invalid and missing numeric inputs; ensure no invalid record is saved.
- Compare several rounding cases against hand calculations.
- Save, reload and reopen a plan; verify persistence.
- Save a scenario; change the baseline plan and reopen the snapshot.
- Export a report; verify totals match the filtered table.
- Test with keyboard navigation and a narrow window.
- After MySQL login, repeat save/reload, scenario and export checks on MySQL.

Record actual expected result, observed result, pass/fail, issue and retest date. Do not claim a manual test passed until you perform it.
