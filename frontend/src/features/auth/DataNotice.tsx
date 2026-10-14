/**
 * The interim data notice a registrant consents to (IR-540; decided on IR-214).
 *
 * It says only what IRIS does today, checked against the code on 2026-10-14:
 *
 * - `RegisterSerializer` stores the name, the email, `consent_given` and a
 *   password through `set_password` (a hash); a Student's program or an
 *   Adviser's college and department go on their profile, and the requested
 *   role becomes a `RoleRequest`.
 * - The verification link is emailed to the address entered
 *   (`send_verification_email`).
 * - Role requests and the user list are read by RDCO alone (`IsAdmin`); system
 *   administrators reach the same rows through the Django admin.
 * - Once approved, an Adviser is listed by `GET /users/advisers/`, open to any
 *   signed-in user, so students can name them as adviser.
 *
 * It claims nothing about retention, deletion, sharing or data-subject
 * requests, because none of those is implemented. The university's Terms of
 * Service and Data Privacy Policy replace it (IR-214).
 */
export function DataNotice() {
  return (
    <div className="space-y-3 text-small text-stone-700">
      <p className="font-semibold text-stone-900">
        Interim notice. The university&apos;s Terms of Service and Data Privacy Policy will
        replace it.
      </p>
      <dl className="space-y-2">
        <div>
          <dt className="font-semibold text-stone-900">What IRIS keeps when you register</dt>
          <dd>
            Your name, your CIT-U email, your college, your program or department, the role you
            ask for, and your password, which is stored only as a hash.
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-stone-900">Why</dt>
          <dd>
            To create your account, to email you a verification link, and to send your role
            request to RDCO.
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-stone-900">Who sees your registration</dt>
          <dd>
            RDCO staff, who approve or decline role requests, and IRIS&apos;s system
            administrators. If you are approved as an Adviser, anyone signed in to IRIS can see
            your name, email, college and department, so students can name you as their adviser.
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-stone-900">Research you submit later</dt>
          <dd>Visible according to its review and publication state.</dd>
        </div>
      </dl>
    </div>
  );
}
