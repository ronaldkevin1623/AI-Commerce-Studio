/**
 * The app mark: a shopping bag with a spark in it.
 *
 * Inline rather than an <img> so it inherits colour from the bar it sits on
 * and stays crisp at any size. The same drawing as public/logo.svg, minus
 * the dark tile — the header already provides its own background, and a
 * second one would show as a square patch against it.
 */
export default function Logo({ size = 22 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="AI Commerce Studio"
    >
      <path
        d="M16 24h32l-2.6 24.2a4 4 0 0 1-4 3.8H22.6a4 4 0 0 1-4-3.8L16 24Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <path
        d="M25 24v-4.5a7 7 0 0 1 14 0V24"
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
      {/* The one piece of colour in the mark, so the eye lands on it. */}
      <path
        d="M32 30.5c1.1 3.4 2.6 4.9 6 6-3.4 1.1-4.9 2.6-6 6-1.1-3.4-2.6-4.9-6-6 3.4-1.1 4.9-2.6 6-6Z"
        fill="#22C55E"
      />
    </svg>
  );
}
