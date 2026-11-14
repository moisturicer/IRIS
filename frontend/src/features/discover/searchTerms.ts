import React from "react";

import { MATCH } from "@/components/ui/highlightRoles";

import { escapeRegExp } from "./discoverUtils";

/**
 * Discover searches by word (IR-1095, spec §4.6). The catalogue endpoint
 * already requires every word it is given, in the title, abstract or authors;
 * what it cannot do is ignore the words of a sentence ("can", "the") or the
 * punctuation stuck to one ("dengue?"). So the page does that before it asks,
 * and the same words are what each card highlights.
 */

/**
 * Function words that say nothing about a paper's subject. Words that can be
 * a subject ("IT", "may", "will") are left out of the list.
 */
const STOPWORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "did", "do", "does",
  "for", "from", "has", "have", "how", "if", "in", "into", "is", "its", "of", "on",
  "or", "should", "so", "that", "the", "their", "there", "these", "this", "those", "to", "was", "were",
  "what", "when", "where", "which", "who", "whom", "whose", "why", "with", "would",
]);

/** Words that open a question in a sentence typed into the search box. */
const QUESTION_WORDS = new Set([
  "what", "why", "how", "when", "where", "who", "whom", "whose", "which",
  "can", "could", "do", "does", "did", "is", "are", "was", "were", "will", "would", "should", "shall",
]);

/** A word, with its inner hyphens and apostrophes ("low-cost", "women's"). */
const WORD = /[\p{L}\p{N}]+(?:[-'’][\p{L}\p{N}]+)*/gu;

function words(text: string): string[] {
  return text.match(WORD) ?? [];
}

/**
 * The words a search is for: lower case, each once, stopwords dropped. When
 * everything typed is a stopword the typed words stay, so a search is never
 * silently emptied.
 */
export function searchTerms(text: string): string[] {
  const all = [...new Set(words(text).map((word) => word.toLowerCase()))];
  const content = all.filter((word) => !STOPWORDS.has(word));
  return content.length > 0 ? content : all;
}

/**
 * Whether a search reads as a question for Ask IRIS: it ends in "?", or opens
 * with a question word and runs to at least three words. The length rule keeps
 * a catalogue search such as "can opener" from being offered a chat.
 */
export function looksLikeQuestion(text: string): boolean {
  const trimmed = text.trim();
  const typedWords = words(trimmed);
  if (typedWords.length === 0) return false;
  if (trimmed.endsWith("?")) return true;
  return typedWords.length >= 3 && QUESTION_WORDS.has(typedWords[0].toLowerCase());
}

/**
 * `text` with each word of `query` that it contains wrapped in a `<mark>`,
 * case-insensitively. Returns the plain string when there is nothing to mark.
 */
export function highlightTerms(text: string | null | undefined, query: string): React.ReactNode {
  const source = text ?? "";
  // Longest first, so "forecasting" is marked whole rather than as "forecast".
  const terms = searchTerms(query).sort((a, b) => b.length - a.length);
  if (terms.length === 0 || !source) return source;

  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  // Split with one capture group puts every match at an odd index.
  const parts = source.split(pattern);
  return React.createElement(
    React.Fragment,
    null,
    ...parts.map((part, i) =>
      i % 2 === 1
        ? React.createElement(
            "mark",
            { key: i, className: `${MATCH} rounded-sm px-px` },
            part,
          )
        : part,
    ),
  );
}
