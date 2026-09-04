import GrowthPage, { CARD } from "../components/growth/GrowthPage";
import RelationshipGraph from "../components/growth/RelationshipGraph";

/**
 * ONE QUESTION: what is any of it reasoning from.
 *
 * The evidence behind every cross-sell and every bundle, drawn so it can be
 * checked rather than taken on trust. Last in the section because it is what
 * you open when you want to interrogate a recommendation, not what you open
 * to run the shop.
 */
export default function MerchantGrowthRelationshipsPage() {
  return (
    <GrowthPage
      title="Relationships"
      subtitle={
        "The evidence behind every cross-sell and every bundle."
      }
    >
      <RelationshipGraph card={CARD} />
    </GrowthPage>
  );
}
