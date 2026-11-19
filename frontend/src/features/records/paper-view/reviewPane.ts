import { createContext, useContext } from "react";

/**
 * What a tab inside Review's pane may ask of the workspace around it
 * (IR-1203). `showReader` makes room for the reader: on a narrow workspace,
 * where the pane covers the paper, it closes the pane. Focus is left to the
 * caller, which moves it to what the reader now shows.
 */
export interface ReviewPane {
  showReader: () => void;
}

export const ReviewPaneContext = createContext<ReviewPane | null>(null);

/** The pane around this tab, or null outside Review (a tab rendered on its own in a test). */
export const useReviewPane = () => useContext(ReviewPaneContext);
