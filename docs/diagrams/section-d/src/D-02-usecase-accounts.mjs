import { A, X, U, UC_LEGEND } from '../tools/dsl.mjs';

export default {
  kind: 'usecase',
  title: 'D-2  Use cases: accounts and access',
  caption: 'From apps/accounts (urls/auth.py, urls/users.py, views.py) and frontend routes on main (IR-1021).',
  system: 'Accounts and access',
  left: [A('Visitor', 'Visitor'), A('User', 'Signed-in user'), A('RDCO', 'RDCO'), A('Admin', 'System Admin')],
  right: [X('Mail', 'Email service')],
  cases: [
    U('UC2', 'Verify email from link'),
    U('UC3', 'Sign in'),
    U('UC4', 'Reset a forgotten password'),
    U('UC1', 'Register with an institutional email and answer the data notice', 170),
    U('UC5', 'Request the Student or Adviser role', 170),
    U('UC6', 'Answer a new data notice; change the AI-use answer', 150),
    U('UC7', 'Edit own profile and photo'),
    U('UC8', 'Download my data'),
    U('UC9', 'Request account deletion'),
    U('UC10', 'Approve or decline role requests', 170),
    U('UC11', 'Lock or unlock an account; view and end sessions', 150),
    U('UC12', "Change a user's role"),
    U('UC13', 'Grant or remove office coordinators; give office roles', 170),
    U('UC14', 'Confirm or reject account deletion', 170),
  ],
  links: [
    ['Visitor', 'UC2', 'UC3', 'UC4', 'UC1'],
    ['User', 'UC6', 'UC7', 'UC8', 'UC9'],
    ['RDCO', 'UC10', 'UC11', 'UC12'],
    ['Admin', 'UC12', 'UC13', 'UC14'],
    ['Mail', 'UC4', 'UC1'],
  ],
  deps: [{ from: 'UC1', to: 'UC5', label: '«include»' }],
  notes: [
    { on: 'UC11', text: 'RDCO only (IsAdmin)' },
    { on: 'UC12', text: 'RDCO gives non-office roles; the System Admin gives office roles', wrap: 130 },
  ],
  legend: [...UC_LEGEND, { tone: 'ext', text: 'external system' }],
};
