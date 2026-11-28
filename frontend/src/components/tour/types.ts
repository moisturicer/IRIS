/**
 * One step of a guided tour (IR-997; shared by every tour since IR-1342).
 *
 * A step points at a DOM id. A step whose target is not reachable is left out
 * of the walk and its count, so a tour never points at nothing.
 */
export interface TourStep {
  id: string;
  /** The DOM id of the control or area this step highlights. */
  target: string;
  title: string;
  body: string;
  /** A short list under the body, one entry per name. */
  items?: { name: string; text: string }[];
}
