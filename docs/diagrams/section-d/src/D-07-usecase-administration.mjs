import { A, U } from '../tools/dsl.mjs';

export default {
  kind: 'usecase',
  title: 'D-7  Use cases: administration',
  caption: 'From the RDCO and Administration screens in frontend/src/lib/access.ts and their API views on main (IR-1021).',
  system: 'Administration',
  left: [A('RDCO', 'RDCO')],
  right: [A('Admin', 'System Admin')],
  cases: [
    U('UC2', 'Decide role requests'),
    U('UC3', 'Decide download requests'),
    U('UC4', 'Decide delete requests'),
    U('UC5', 'Import records from Excel'),
    U('UC6', 'Publish a new data notice version', 170),
    U('UC12', 'View and end user sessions (API only, no screen)', 130),
    U('UC1', 'Manage users and roles'),
    U('UC7', 'Read every data notice version', 170),
    U('UC8', 'Read and export the audit log (CSV)', 170),
    U('UC9', 'Set retention periods'),
    U('UC10', 'Confirm or reject account deletions', 170),
    U('UC11', 'Grant office roles and coordinators', 170),
  ],
  links: [
    ['RDCO', 'UC2', 'UC3', 'UC4', 'UC5', 'UC6', 'UC12', 'UC1', 'UC7'],
    ['Admin', 'UC1', 'UC7', 'UC8', 'UC9', 'UC10', 'UC11'],
  ],
  legend: [{ line: 'solid', text: 'actor takes part' }],
};
