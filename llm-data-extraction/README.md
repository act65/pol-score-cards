Extracting info from public political discourse.

Once we have the raw text data, we can use LLMs to extract information from it.

Key questions

- how much context (length) is needed / should be used?
- How accurate are the predictions of the model used?
    - vs other LLMs


Some of the attributes cannot be trusted to the knowledge of a LLM.

- Strength requires us to verify promises (turned into policies)
- Divination requires us to verify predictions
- Authenticity requires us to align public statements with parliamentary and council / committee records
- Veracity requires us to verify claims


## Usage

```
python extract.py ../data/data/greens_media_releases.json specificity $OPENAI_API_KEY green-specificity.json
```