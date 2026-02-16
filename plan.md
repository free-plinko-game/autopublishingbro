# Implementation Plan: `/api/transform` Endpoint

## Context

AirOps (corporate-approved workflow tool) handles the UI and LLM content generation, but cannot do ACF field transformation. Our Flask API on Digital Ocean handles that transformation. AirOps then makes the final WordPress REST API call itself — bypassing Cloudflare's bot protection since AirOps is a trusted source.

**Flow:**
```
AirOps                          Droplet                    WordPress
──────                          ───────                    ─────────
1. User fills form
2. LLM generates content
3. HTTP POST ──────────────────► /api/transform
                                 Transforms to ACF format
4. Receives ACF payload ◄─────── Returns JSON
5. HTTP POST ─────────────────────────────────────────────► /wp-json/wp/v2/posts
                                                            Post created! ✅
```

## Files to Modify

| File | Changes |
|---|---|
| `api/routes.py` | Add `require_api_key` decorator, `_get_mapping_for_site()`, `_normalize_airops_sections()`, `_validate_transform_request()`, and `transform()` endpoint |
| `tests/test_api.py` | Add `TestTransform` and `TestNormalizeAiropsSections` test classes; update `app` fixture to set `TRANSFORM_API_KEY` env var |
| `.env` | Add `TRANSFORM_API_KEY` |
| `PROJECT_SPEC.md` | Document the new endpoint |

**No changes needed** to `app.py`, `acf/transformer.py`, or `acf/defaults.py`. The endpoint registers automatically via the existing `api_bp` blueprint.

---

## 1. API Key Authentication

A `require_api_key` decorator in `api/routes.py`:
- Reads `TRANSFORM_API_KEY` from `os.environ`
- Returns **500** if env var not configured on server
- Returns **401** if `X-API-Key` header missing from request
- Returns **403** if key doesn't match (uses `hmac.compare_digest` to prevent timing attacks)

```python
import functools, hmac

def require_api_key(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        api_key = os.environ.get("TRANSFORM_API_KEY")
        if not api_key:
            return jsonify({"error": "Server misconfiguration: API key not set"}), 500
        provided = request.headers.get("X-API-Key", "")
        if not provided:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        if not hmac.compare_digest(provided, api_key):
            return jsonify({"error": "Invalid API key"}), 403
        return f(*args, **kwargs)
    return decorated
```

---

## 2. Input Normalization

AirOps sends a flat format; our transformer expects nested format:

| AirOps sends | Transformer expects |
|---|---|
| `"layout": "BasicContent"` | `"acf_fc_layout": "BasicContent"` |
| `"heading": "Title"` (string) | `"heading": {"text": "Title"}` (nested dict) |
| `"heading_level": "h1"` | merged into `"heading": {"level": "h1"}` |
| all other keys | pass through as-is |

If `heading` is already a dict (future-proofing), it passes through unchanged.

New helper: `_normalize_airops_sections(raw_sections) -> list[dict]`

---

## 3. Site-Specific Mapping

New helper: `_get_mapping_for_site(site_name) -> FieldMapping`
- Looks for `config/field_mappings/{site_name}.json`
- Falls back to default from app config
- Convention-over-configuration: add a new site by dropping a mapping file

---

## 4. The Endpoint

```
POST /api/transform
Headers: X-API-Key: <key>
```

**Input:**
```json
{
  "site": "sunvegascasino",
  "template": "pokies_category",
  "variables": {
    "category_name": "Single-Reel Pokies",
    "category_slug": "single-reel-pokies",
    "cta_list_id": "123"
  },
  "sections": [
    {
      "layout": "BasicContent",
      "heading": "Single-Reel Pokies",
      "heading_level": "h1",
      "content": "<p>Pre-generated HTML from AirOps LLM</p>"
    }
  ],
  "status": "draft"
}
```

**Output:**
```json
{
  "success": true,
  "payload": {
    "title": "Single-Reel Pokies",
    "slug": "single-reel-pokies",
    "status": "draft",
    "acf": {
      "page_sections": [
        {
          "acf_fc_layout": "BasicContent",
          "heading": {"text": "Single-Reel Pokies", "level": "h1", "alignment": {"desktop": "inherit", "mobile": "inherit"}},
          "content": "<p>Pre-generated HTML from AirOps LLM</p>",
          "section_id": "",
          "padding_override": "reduced-padding",
          "section_width": "narrow",
          "toc_exclude": false,
          "background_color": "",
          "background_image": ""
        }
      ]
    }
  },
  "warnings": []
}
```

**Processing flow:**
1. `@require_api_key` — auth check
2. Parse JSON body, validate required fields (`site`, `sections`)
3. Load site-specific field mapping
4. Normalize AirOps sections → transformer format
5. `validate_sections()` → collect warnings (non-blocking)
6. `transform_to_acf()` → ACF REST payload with defaults
7. Build payload: title (from `variables.category_name` or first heading), slug (from `variables.category_slug`), status, ACF data
8. Return `{"success": true, "payload": {...}, "warnings": [...]}`

---

## 5. Tests (~15 cases)

**Auth tests** (3): missing header → 401, wrong key → 403, missing env var → 500

**Validation tests** (4): no JSON → 400, missing site → 400, missing sections → 400, sections not a list → 400

**Success tests** (3): full transform with title/slug/status, heading normalization verified, warnings returned

**Error tests** (1): mapping load failure → 500

**Normalization unit tests** (5): layout rename, heading+level nesting, heading-only, passthrough fields, empty list

---

## Verification

```bash
# Run just the new tests
python -m pytest tests/test_api.py -k "TestTransform or TestNormalize" -v

# Run full suite to confirm no regressions
python -m pytest -v
```
