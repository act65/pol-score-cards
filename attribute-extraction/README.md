Here's a table summarizing the trust level for an LLM to perform the *entire scoring task* for each attribute, along with its primary role if it can't do the full scoring, and what external verification is needed.

| Attribute       | LLM Trust for Full Scoring | Primary LLM Role (if not full scoring)                                  | External Verification / Data Needed                                                                                                |
|-----------------|----------------------------|-------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| **Forthrightness**| High                       | Direct scoring based on Q&A analysis                                    | None (assuming Q&A pairs are provided and clearly demarcated)                                                                      |
| **Strength**      | Low                        | Identify promises from text; potentially identify policy documents      | Policy databases, legislative records, news reports on implementation; **human judgment** to link promises to policies.            |
| **Veracity**      | Low                        | Identify factual claims                                                 | Fact-checking databases (e.g., PolitiFact, Snopes, official statistics), expert knowledge to verify claims.                        |
| **Authenticity**  | Low-Medium                 | Extract public statements; extract actions from *provided* records; compare | Official voting records, parliamentary transcripts, committee reports; **human judgment** to verify and source these records and assess true consistency. |
| **Divination**    | Low                        | Identify predictions from text                                          | Historical data, economic/social outcomes *after* the prediction timeframe to verify accuracy.                                     |
| **Charisma**      | Low-Medium                 | Analyze rhetoric for persuasive language, calls for consensus, tone of negotiation. Potentially identify instances of cross-party mentions. | Voting records (cross-party successes), news on successful negotiations, (subjective) peer assessments. Hard to quantify objectively. |
| **Civility**      | High                       | Direct scoring based on language analysis (tone, insults, respect)      | None                                                                                                                               |
| **Rigor**         | Medium-High                | Identify logical fallacies; check for cited evidence within the text    | Potentially human review for complex fallacies. If "evidence-based" means *validity* of evidence, then links to Veracity.         |
| **Specificity**   | High                       | Direct scoring based on vagueness/concreteness of statements            | None                                                                                                                               |

Summary of Tasks for Attributes Not Fully Trustworthy for LLM Scoring
---------------------------------------------------------------------

For attributes where LLMs cannot perform the entire scoring task, a multi-step process involving LLM assistance and external verification is needed:

1.  **Strength**:
    *   **LLM Role**:
        *   Scan manifestos, speeches, press releases, debate transcripts to extract explicit "promises" or strong commitments. (e.g., "We will build X hospitals," "I pledge to lower Y tax").
        *   Potentially, scan legislative databases and government announcements for keywords related to these promises to find *potential* policy implementations.
    *   **External Verification / Human Role**:
        *   Curate and validate the LLM-extracted list of promises.
        *   Research official government sources (policy documents, legislative acts, budget allocations, official reports) to confirm if a policy corresponding to the promise was enacted and implemented.
        *   **Crucial Human Judgment**: Determine if the implemented policy genuinely fulfills the spirit and letter of the original promise. This can be subjective (e.g., a watered-down version).
        *   Define a timeframe for "trackable" promises (e.g., promises made for the current term where sufficient time has passed to assess fulfillment).
        *   **Metric Calculation**: `(Number of fulfilled promises / Total trackable promises made) * 100`.

2.  **Veracity**:
    *   **LLM Role**:
        *   Extract specific, verifiable factual claims from the politician's statements. (e.g., "Unemployment has fallen by X%," "We invested Y amount in Z sector").
    *   **External Verification / Human Role**:
        *   For each claim, consult reputable fact-checking websites (e.g., PolitiFact, Snopes, Full Fact), official statistical agencies, academic studies, or expert sources.
        *   Categorize each claim (e.g., True, Mostly True, Half True, Mostly False, False, Misleading, Unverifiable).
        *   **Metric Calculation**: Could be a ratio like `(Number of True/Mostly True claims / Total verifiable claims) * 100`, or a penalty system for false/misleading claims.

3.  **Authenticity**:
    *   **LLM Role**:
        *   Extract key public statements, positions, and promises on specific issues.
        *   From *provided* parliamentary records (e.g., Hansard, voting logs), extract relevant speeches, voting actions, and committee work related to those same issues.
        *   Perform an initial semantic comparison between public statements and parliamentary actions.
    *   **External Verification / Human Role**:
        *   Source and verify the parliamentary records.
        *   **Crucial Human Judgment**: Assess if the parliamentary actions are genuinely consistent with public statements. This requires understanding context, nuance, and potential justifiable shifts in position versus clear contradictions.
        *   **Metric Calculation**: Could be a qualitative assessment or a ratio `(Number of consistent statement-action pairs / Total examined pairs) * 100`.

4.  **Divination**:
    *   **LLM Role**:
        *   Extract clear, specific, and ideally time-bound predictions made by the politician (e.g., "The economy will grow by X% next year," "This policy will lead to Y outcome within Z months").
    *   **External Verification / Human Role**:
        *   Once the timeframe for the prediction has passed, gather actual data on the outcome from official sources (economic reports, social statistics, event records).
        *   Compare the prediction with the actual outcome.
        *   **Metric Calculation**: `(Number of accurate predictions / Total verifiable predictions made) * 100`.

5.  **Charisma** (This is particularly tricky to quantify):
    *   **LLM Role**:
        *   Analyze rhetoric for persuasive language, calls for unity, inclusive language, and mentions of cross-party collaboration or consensus-building efforts.
        *   Identify instances where the politician explicitly states they are trying to persuade or build consensus.
    *   **External Verification / Human Role**:
        *   Examine voting records for successful cross-party amendments or bills championed by the politician.
        *   Review news reports and analyses for evidence of successful negotiation or consensus-building led by the politician.
        *   This attribute might benefit from qualitative analysis or a composite score of indirect indicators rather than a simple quantitative metric. It's hard to separate from party discipline or broader political currents.

6.  **Rigor** (The "evidence-based reasoning" part, if it implies *validity* of evidence):
    *   **LLM Role**:
        *   Identify claims and check if any evidence is *cited* within the text.
        *   Identify logical fallacies (this part is Medium-High trust for LLM).
    *   **External Verification / Human Role**:
        *   If evidence is cited, the *validity and accuracy* of that evidence would need to be checked, linking this aspect of Rigor to the Veracity process.
        *   Review complex arguments for subtle fallacies that an LLM might miss.
        *   **Metric Calculation**: Could be a score based on fallacy frequency, combined with a check on whether claims are at least *accompanied* by purported evidence (validity of evidence is a separate Veracity check).

## Usage

```
python extract.py ../data/data/greens_media_releases.json specificity $OPENAI_API_KEY green-specificity.json
```