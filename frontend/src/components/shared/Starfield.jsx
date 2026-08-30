import "../../styles/starfield.css";

/**
 * The background the app sits on.
 *
 * Three layers of stars drifting upward at different speeds, over a radial
 * gradient. Deliberately inert: fixed, pointer-events none, and behind
 * everything at z-index 0, so it can never intercept a click or shift the
 * layout of the thing it sits behind.
 *
 * The sidebar and every panel keep their own opaque backgrounds, so this
 * shows only where the app was empty — which is where it was asked for.
 */
export default function Starfield() {
  return (
    <div className="starfield" aria-hidden="true">
      <span className="stars-1" />
      <span className="stars-2" />
      <span className="stars-3" />
    </div>
  );
}
