import GrowthPage, { CARD } from "../components/growth/GrowthPage";
import CampaignPanel from "../components/growth/CampaignPanel";

/**
 * ONE QUESTION: what is running.
 *
 * A campaign is a goal, an envelope and a window, and it can end four ways.
 * That is a different kind of object from a single proposal, which is why it
 * gets its own page rather than a block underneath the queue.
 */
export default function MerchantGrowthCampaignsPage() {
  return (
    <GrowthPage
      title="Campaigns"
      subtitle={
        "What is running, and the four ways it can stop."
      }
    >
      <CampaignPanel card={CARD} />
    </GrowthPage>
  );
}
