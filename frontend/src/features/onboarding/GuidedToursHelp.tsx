import { Link } from "react-router-dom";

import { TOUR_PAGES } from "./studentTours";

/**
 * Settings › Help's "Guided tours" (IR-1342, AC 5): the one place a student
 * takes a tour again. Each link opens its page with `?tour=<key>`, which
 * starts the tour whether or not it was seen. Pages have no tour button.
 */
export function GuidedToursHelp() {
  return (
    <>
      <p>
        Each page walks you through itself the first time you open it, and so does Publish. Take a
        tour again here whenever you like.
      </p>
      <ul>
        {TOUR_PAGES.map(({ key, page, href }) => (
          <li key={key}>
            <strong className="font-semibold text-stone-900">{page}</strong>{" "}
            <Link to={href} className="font-medium text-brand underline underline-offset-2">
              Take the tour<span className="sr-only">: {page}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
