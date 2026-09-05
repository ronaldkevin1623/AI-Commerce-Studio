import GrowthPage, { CARD } from "../components/growth/GrowthPage";
import AttributionPanel from "../components/growth/AttributionPanel";

/**
 * ONE QUESTION: what came of it.
 *
 * The closing half of the loop, and the only page here that reports outcome
 * rather than intent. It is kept away from the proposal queue deliberately:
 * a screen showing what an agent WANTS to spend directly above what it HAS
 * earned invites the two to be read as one number.
 */
export default function MerchantGrowthAttributionPage() {
  return (
    <GrowthPage
      title="Attribution"
      subtitle={
        "What the margin committed to agent offers actually bought."
      }
    >
      <AttributionPanel card={CARD} />
    </GrowthPage>
  );
}
