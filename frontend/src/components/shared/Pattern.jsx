import "../../styles/pattern.css";

/**
 * The background the app sits on.
 *
 * A fine grid over a near-black ground. Deliberately inert: fixed,
 * pointer-events none, and behind everything at z-index 0, so it can never
 * intercept a click or shift the layout of what sits on top.
 *
 * The sidebar and every panel keep their own opaque backgrounds, so this
 * shows only where the app was empty — which is where it was asked for.
 */
export default function Pattern() {
  return <div className="pattern-backdrop" aria-hidden="true" />;
}
