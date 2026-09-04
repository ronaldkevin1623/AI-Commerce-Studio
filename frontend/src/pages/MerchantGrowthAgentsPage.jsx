import GrowthPage, { CARD } from "../components/growth/GrowthPage";
import GrowthQueue from "../components/growth/GrowthQueue";

/**
 * ONE QUESTION: what wants to happen to my margin.
 *
 * First in the section and first in the sidebar, because a queue of actions
 * waiting on a decision outranks any report of what already happened. It
 * used to sit at the top of a page with five other things under it, which
 * put the answer in the right place and the rest of the page in the way.
 */
export default function MerchantGrowthAgentsPage() {
  return (
    <GrowthPage
      title="Agents"
      subtitle={
        "What is waiting on a decision. Nothing on this page has been applied."
      }
    >
      <GrowthQueue card={CARD} />
    </GrowthPage>
  );
}
