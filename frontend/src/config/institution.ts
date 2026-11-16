import logo from "@/assets/images/cit-logo.png";
import seal from "@/assets/images/cit-seal.png";

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
  /**
   * The logo's emblem alone, square, for widths where the full logo's words
   * would be too small to read (below 480 px; IR-1098, audit RES-05).
   */
  seal: string;
  /** The domain institutional email addresses use. */
  emailDomain: string;
}

export const INSTITUTION: Institution = {
  name: "Cebu Institute of Technology – University",
  shortName: "CIT-U",
  logo,
  seal,
  emailDomain: "cit.edu",
};
