/** Scroll-driven entrances start invisible and wait for the viewport — a printer never scrolls.
 *  Add this to any Reveal / Stagger / StaggerItem so `@media print` forces the settled state
 *  (the `!` beats the inline styles motion writes). */
export const PRINT_SAFE = "print:opacity-100! print:transform-none! print:filter-none! print:[clip-path:none]!";
