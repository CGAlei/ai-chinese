Already done! enrich_dict.py was created at the end of my previous response. Here's a quick usage guide:

Test first with dry-run (no API calls):

bash
python enrich_dict.py dictionary.json --dry-run
Run with OpenAI (recommended — cost is negligible):

bash
export OPENAI_API_KEY="sk-..."
python enrich_dict.py dictionary.json
Run with OpenRouter instead:

bash
export OPENROUTER_API_KEY="sk-or-..."
python enrich_dict.py dictionary.json --provider openrouter
# Or pick a specific model:
python enrich_dict.py dictionary.json --provider openrouter --model anthropic/claude-3-haiku
The output will always be saved as dictionary_enriched.json next to your original. The original is never touched. Import the enriched file back into the reader using the 📂 dictionary import button.

Key things the script handles automatically:

Skips entries that already have / separators (already good)
Only processes raw single-word Google Translate entries
Saves progress even if you press Ctrl+C mid-way
Continues to next batch if one batch fails