# Module 7: KPI Dashboard & Analytics

---

## FR-M7-01 — Role-Differentiated Pipeline Monitoring Dashboard

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Student
actor "Staff Reviewer\n(Adviser / RDCO / ITSO /\nKTTO / IERC)" as Staff
actor Admin
actor System

rectangle "Module 7 : KPI Dashboard & Analytics" {
  usecase "View Personal Dashboard (Student)" as UC1
  usecase "See Own Submitted Records + Statuses" as UC2
  usecase "View Staff Pipeline Dashboard" as UC3
  usecase "See Records in Own Review Queue" as UC4
  usecase "See Average Processing Time per Stage" as UC5
  usecase "See Counts by Pipeline Status" as UC6
  usecase "View Admin Overview Dashboard" as UC7
  usecase "Refresh Dashboard Data" as UC8
}

Student --> UC1
UC1     ..> UC2 : include
Staff   --> UC3
UC3     ..> UC4 : include
UC3     ..> UC5 : include
UC3     ..> UC6 : include
Admin   --> UC7
UC7     ..> UC5 : include
UC7     ..> UC6 : include
UC1     ..> UC8 : extend
UC3     ..> UC8 : extend
UC7     ..> UC8 : extend
System  --> UC8
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M7-01 |
| **Name** | Role-Differentiated Pipeline Monitoring Dashboard |
| **Actors** | Student (primary), Staff Reviewer, Admin, System |
| **Preconditions** | User is authenticated |
| **Main Flow — Student** | 1. Student navigates to Dashboard 2. System displays the student's own submitted records with their current `pipeline_status` 3. Student sees Draft, Under Review, Published, Declined counts |
| **Main Flow — Staff Reviewer** | 1. Staff navigates to Dashboard 2. System displays records in the staff member's pipeline queue (role-filtered) 3. Dashboard shows: count of pending reviews, average processing time per stage, status breakdown |
| **Main Flow — Admin** | 1. Admin views an overview dashboard with all pipeline stages, all roles, institution-wide counts and processing times |
| **Refresh** | Dashboard data refreshes on page load; manual refresh button available |
| **Postconditions** | Dashboard reflects the current state of the pipeline for the user's role |

> **Planned endpoint — not yet implemented:** `GET /reviews/analytics/` — returns per-stage average processing time (average days a record spends at each review stage, computed from `Review` timestamps, excluding in-flight records). Planned for a future sprint; stub returns HTTP 501.

### Activity Diagram
```plantuml
@startuml
start
:User opens Dashboard;
if (User role = Student?) then (Yes)
  :Fetch records WHERE owner = user;
  :Aggregate counts by pipeline_status;
  :Display: Draft | Under Review | Published | Declined;
else if (User role = Staff Reviewer?) then (Yes)
  :Fetch records in role's pipeline stage(s);
  :Calculate average processing time per stage;
  :Count records by status;
  :Display queue + KPIs;
else (Admin)
  :Fetch institution-wide pipeline data;
  :Aggregate all stages, all roles;
  :Display full overview + trend data;
endif
if (User clicks Refresh?) then (Yes)
  :Re-fetch data from API;
  :Update dashboard widgets;
else (No)
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Dashboard (Student View)
  ==
  My Records Overview
  {
    {+
      Draft
      --
      2
    }
    |
    {+
      Under Review
      --
      1
    }
    |
    {+
      Published
      --
      5
    }
    |
    {+
      Declined
      --
      0
    }
  }
  .
  Recent Records
  {#
  Title                        | Status          | Date
  Smart Irrigation System      | 🔵 RDCO Intake  | 2026-05-25
  Blockchain Credentials       | ✅ Published    | 2026-04-10
  }
}
@endsalt
```

```plantuml
@startsalt
{+
  IRIS > Dashboard (RDCO Staff View)       [🔄 Refresh]
  ==
  {
    {+
      Intake Pending
      --
      4
    }
    |
    {+
      Final Review
      --
      2
    }
    |
    {+
      Avg. Time
      --
      3.2 days
    }
  }
  .
  Records Awaiting Intake Review
  {#
  Record                 | Type    | Submitted  | Action
  Smart Irrigation...    | Project | 2026-05-25 | [Review]
  Blockchain Credentials | Thesis  | 2026-05-24 | [Review]
  }
}
@endsalt
```

---

## FR-M7-02 — Report Generation and Export

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "Staff Admin" as Admin
actor System

rectangle "Module 7 : KPI Dashboard & Analytics" {
  usecase "Select Report Filters" as UC1
  usecase "Filter by Year" as UC2
  usecase "Filter by Department" as UC3
  usecase "Filter by Record Type" as UC4
  usecase "Filter by IP Classification" as UC5
  usecase "Generate Summary Report" as UC6
  usecase "Display Aggregate Counts + Trends" as UC7
  usecase "List Matching Records" as UC8
  usecase "Export Report as .xlsx" as UC9
}

Admin --> UC1
UC1   ..> UC2 : extend
UC1   ..> UC3 : extend
UC1   ..> UC4 : extend
UC1   ..> UC5 : extend
UC1   ..> UC6 : include
UC6   ..> UC7 : include
UC6   ..> UC8 : include
Admin --> UC9
UC9   ..> UC6 : include
System --> UC9
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M7-02 |
| **Name** | Report Generation and Export |
| **Actors** | Staff Admin (primary), System |
| **Preconditions** | Admin is authenticated; records exist in the database |
| **Main Flow** | 1. Admin navigates to the Reports section 2. Admin selects filter criteria: Year, Department, Record Type, IP Classification 3. Admin clicks "Generate Report" 4. System queries records matching the filter criteria 5. Report displays: aggregate counts, trend data (records per year), listing of matching records 6. Admin clicks "Export as .xlsx" 7. System generates the Excel file using pyexcel-xlsx 8. Browser downloads the report file |
| **Alternative Flow A** | No records match the filters → Report shows zero counts and empty listing |
| **Alternative Flow B** | Export with no filter applied → Full institution-wide report generated |
| **Postconditions** | Report displayed on-screen; .xlsx file downloadable with aggregate counts, trends, and record listing |

### Activity Diagram
```plantuml
@startuml
start
:Admin opens Reports page;
:Admin selects filter criteria:
  Year | Department | Record Type | IP Classification;
:Admin clicks "Generate Report";
:System queries records matching selected filters;
if (No records match?) then (Yes)
  :Show empty report (zero counts);
else (No)
  :Compute aggregate counts by status, type, year;
  :Compute trend: records per year;
  :List matching records with key metadata;
  :Display report on screen;
endif
if (Admin clicks "Export as .xlsx"?) then (Yes)
  :Build Excel workbook using pyexcel-xlsx:
    Sheet 1: Summary / Aggregate Counts
    Sheet 2: Trend Data (by year)
    Sheet 3: Record Listing;
  :Stream .xlsx file to browser;
else (No)
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Reports
  ==
  Generate Report
  --
  Year:              | ^2024          ^
  Department:        | ^All Depts     ^
  Record Type:       | ^All Types     ^
  IP Classification: | ^Patent        ^
  .
  [            Generate Report            ]
  ==
  Report: Patents · 2024 · All Departments
  --
  Summary
  {#
  Metric         | Count
  Total Records  | 18
  Published      | 15
  In Pipeline    | 3
  Declined       | 0
  }
  .
  Matching Records
  {#
  Title                   | Type    | Year | Status
  Smart Irrigation...     | Thesis  | 2024 | Published
  Blockchain Credentials  | Project | 2024 | Published
  }
  .
  [⬇ Export as .xlsx]
}
@endsalt
```
