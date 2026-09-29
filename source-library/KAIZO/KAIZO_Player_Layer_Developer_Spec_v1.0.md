# KAIZO Player Layer
## Developer Handover — Final Functional Discussion

**Project:** KAIZO Coaching Intelligence System  
**Core:** KAIZO Core v2.1 — Frozen  
**Slogan:** Better Every Day

## 1. Strategic Direction
KAIZO expands from a coach-focused system into:
- **KAIZO COACH:** professional interface for coaches, technical directors, clubs and youth-sector management.
- **KAIZO ATHLETE / PLAYER LAYER:** simplified athlete interface connected to the same KAIZO Core and Knowledge Base.

The Player Layer is not a separate system and must not duplicate the Knowledge Base.

## 2. Player Layer — MVP
### A. Player Profile
- Player ID
- Age
- Gender
- Weight category
- Technical level
- Competition level
- Club / Academy
- Coach
- Training status

### B. Tests & Progress
- Physical and technical tests
- Raw scores
- Percentiles where validated normative data exists
- Normative levels
- Progress trends
- Belt Exam Roadmap
- Readiness for next belt
- Remaining skills
- Radar / Spider Chart

**Scientific rule:** arbitrary thresholds must not be presented as scientific norms. Every normative test must document source, population, age range, sex, protocol, unit and interpretation method. If no validated external norm exists, label it **KAIZO Internal Benchmark**.

### C. Problem Solver
Problem → Possible Cause → Reference Explanation → Approved External Video → Corrective Drill → Practice → Retest

### D. My Drills
- Coach-assigned or KAIZO-recommended drills
- Objective
- Prescription
- Sets / repetitions / duration
- External video URL
- Due date
- Status
- Result

## 3. Video Policy
KAIZO must **not store video files**. Store only video metadata and verified references.

## 4. Technical & Biomechanical Hub
Future support includes technical video references, Kuzushi → Tsukuri → Kake references, Tokui-waza submission, coach feedback, and Kinovea analysis results. KAIZO does not need to become a video-analysis engine.

## 5. Competition & Tactical Record
Future support: match records, Kumi-kata tagging, successful throws, failed attacks, tactical patterns and recurrent problems.

## 6. Digital Identity & Engagement
Digital Player Card, Medal Cabinet, KAIZO Points and optional leaderboard.

## 7. Parent Portal
Future support: attendance, technical/physical progress, behaviour, reports and subscription status with authorized data access.

## 8. Commercial Architecture
Future models include FREE, PLAYER PRO, COACH PRO, CLUB/ACADEMY and FEDERATION/ORGANIZATION. MVP should not implement every tier.

## 9. Player Data Model
Players, Tests, Test Results, Problems, External Videos, and Player Drill Assignments are linked through stable IDs.

## 10. Main Performance Relationship
Player → Test Result → Performance Gap → Problem → Possible Cause → Technique → Corrective Drill → External Video → Practice → Retest → Measured Improvement

## 11. Coach ↔ Player Feedback
The coach should be updated when the player completes drills, records tests, reports problems or completes corrective tasks.

## 12. Core Freeze Rule
**KAIZO Core v2.1 remains FROZEN.** No new Core Engine should be created merely to support the Player Layer.

## 13. Development Phases
Phase 1: Player Profile, Tests & Progress, Problem Solver, My Drills.
Phase 2: Technical Expansion and Competition Record.
Phase 3: Family & Engagement.
Phase 4: Commercial Expansion.

## 14. Required Programmer Deliverables
ERD, API specification and UI/UX wireframes before major coding.

## 15. MVP Success Criterion
Create Profile → Take Test → Receive Result → Identify Problem → Watch Approved External Video → Perform Corrective Drill → Record Completion → Retest → See Progress → Coach Sees Update

## Final Product Principle
KAIZO should become a system that converts performance data into a problem, the problem into a solution, and the solution into measurable improvement.

**KAIZO — Better Every Day**