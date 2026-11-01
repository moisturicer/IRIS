import logo from "@/assets/images/cit-logo.png";

/**
 * The institution this deployment serves (IR-768).
 *
 * IRIS owns the platform identity; each university owns its institutional
 * identity. ADR-005 gives every institution its own deployment, so the
 * institution is a property of the deployment, and this module is the one
 * place the interface reads it from. Copy that needs no name stays neutral
 * ("your institution", "an administrator"); copy that does reads it here.
 *
 * CIT-U is the pilot institution. Another deployment changes these values,
 * not the screens.
 */
export interface Institution {
  /** Full name, as on the logo and in the footer. */
  name: string;
  /** Short form, for space-constrained labels. */
  shortName: string;
  /** The institution's logo, shown beside the IRIS mark. */
  logo: string;
  /** The domain institutional email addresses use. */
  emailDomain: string;
}

export const INSTITUTION: Institution = {
  name: "Cebu Institute of Technology – University",
  shortName: "CIT-U",
  logo,
  emailDomain: "cit.edu",
};
