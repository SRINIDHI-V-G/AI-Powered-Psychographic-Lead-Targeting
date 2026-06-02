"""
Enrichment provider package — Phase B3 stub.

Enrichment providers extract market intelligence (buyer motivations,
pain points, decision criteria) from review datasets and structured sources.

Architecture contract:
  - Enrichment providers NEVER create discovered_users rows.
  - Enrichment providers NEVER create leads.
  - Output flows into: motivation generation prompts, OCEAN context.
  - Output NEVER modifies user NLP features or user OCEAN scores directly.

Implementations scheduled for Phase B3:
  - AmazonDatasetProvider  (UCSD Amazon Reviews public dataset)
  - TrustpilotProvider     (product review categories)
  - G2Provider             (software product reviews)
  - CapterraProvider       (software product reviews)
  - MouthShutProvider      (India-specific consumer reviews)
"""
