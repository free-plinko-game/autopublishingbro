# WordPress ACF Content Automation System

## Project Overview

A Flask-based application that automates content creation and publishing to WordPress sites using Advanced Custom Fields (ACF) Pro Flexible Content. The system uses LLMs to generate content based on templates, then transforms and publishes via the WordPress REST API.

### The Problem

ACF Flexible Content fields have deeply nested, cryptic field keys like:
```
acf[field_61042266f0b46][row-0][field_6104227ef0b47_field_611e64259a1e0_field_6104216716976][field_6104217816977]
```

These are unmappable by humans and impossible for LLMs to work with directly. We need a translation layer.

### The Solution

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │     │                 │
│  JSON Template  │────▶│  LLM Fills In   │────▶│  Transform to   │────▶│  WordPress      │
│  (Human-readable)│     │  Content        │     │  ACF Format     │     │  REST API       │
│                 │     │                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Architecture

### Tech Stack

- **Backend**: Flask (Python 3.11+)
- **LLM Integration**: Anthropic Claude API (or OpenAI compatible)
- **WordPress Communication**: REST API with Application Passwords
- **Configuration**: YAML for templates, JSON for field mappings
- **Database**: SQLite for job tracking (optional, can be stateless)

### Directory Structure

```
wp-content-automation/
├── app.py                      # Flask application entry point
├── config/
│   ├── settings.py             # App configuration
│   ├── wordpress_sites.yaml    # WordPress site credentials
│   └── field_mappings/         # Generated ACF field mappings
│       └── sunvegascasino.json
├── acf/
│   ├── parser.py               # Parses ACF export JSON
│   ├── mapper.py               # Maps human names ↔ ACF field keys
│   └── transformer.py          # Transforms LLM output → ACF format
├── templates/
│   ├── base_templates/         # Reusable section templates
│   │   ├── basic_content.yaml
│   │   ├── gambling_operators.yaml
│   │   └── accordion_section.yaml
│   └── page_templates/         # Full page compositions
│       ├── slot_review.yaml
│       ├── casino_guide.yaml
│       └── pokies_category.yaml
├── llm/
│   ├── client.py               # LLM API wrapper
│   ├── prompts.py              # System prompts for content generation
│   └── content_generator.py    # Orchestrates content generation
├── wordpress/
│   ├── client.py               # WordPress REST API client
│   ├── auth.py                 # Authentication handling
│   └── media.py                # Media upload handling
├── api/
│   └── routes.py               # Flask API endpoints
├── utils/
│   ├── validators.py           # Input validation
│   └── html_sanitizer.py       # Clean HTML for WYSIWYG fields
├── tests/
│   └── ...
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Core Components

### 1. ACF Parser (`acf/parser.py`)

**Purpose**: Parse the ACF JSON export and extract field structures.

**Input**: ACF export JSON file (the 22k line monster)

**Output**: Structured mapping of all field groups, layouts, and fields

**Key Challenges**:
- ACF uses "clone" fields that reference other field groups
- Flexible Content layouts contain nested sub_fields
- Field keys are UUIDs that need mapping to human names
- Deeply nested groups (Heading → heading → text, level, alignment → desktop, mobile)

**Required Functions**:
```python
def parse_acf_export(filepath: str) -> dict:
    """Parse full ACF export, return structured field map"""
    
def resolve_clone_fields(field: dict, all_groups: dict) -> dict:
    """Recursively resolve clone fields to their actual field definitions"""
    
def extract_flexible_content_layouts(field_group: dict) -> list:
    """Extract all layouts from a Flexible Content field"""
    
def build_field_tree(fields: list, all_groups: dict) -> dict:
    """Build nested field structure with resolved clones"""
```

**Output Structure**:
```python
{
    "page_sections": {
        "field_key": "field_61042266f0b46",
        "type": "flexible_content",
        "layouts": {
            "BasicContent": {
                "layout_key": "layout_6104226d4285a",
                "fields": {
                    "section_id": {"key": "field_607dbe7d30c4e", "type": "text"},
                    "padding_override": {"key": "field_604fb9aff2bef", "type": "select", "choices": [...]},
                    "heading": {
                        "text": {"key": "field_6104217816977", "type": "text"},
                        "level": {"key": "field_6104217f16978", "type": "select", "choices": ["h1".."h6"]},
                        "alignment": {
                            "desktop": {"key": "field_611278c0063b5", "type": "select"},
                            "mobile": {"key": "field_611278ea063b6", "type": "select"}
                        }
                    },
                    "content": {"key": "field_611e64259a296", "type": "wysiwyg"}
                }
            },
            "GamblingOperators": {
                "layout_key": "layout_...",
                "fields": {
                    "section_id": {...},
                    "heading": {...},
                    "shortcode": {"key": "field_6120037c1998c", "type": "text", "required": true},
                    "table_appearance": {...},
                    "content_above": {"key": "field_6120051e89b55", "type": "wysiwyg"},
                    "content_below": {"key": "field_6120052e89b56", "type": "wysiwyg"},
                    "call_to_action": {"key": "field_6120056089b57", "type": "link"}
                }
            }
            # ... other layouts
        }
    }
}
```

---

### 2. ACF Transformer (`acf/transformer.py`)

**Purpose**: Transform human-readable JSON to ACF REST API format.

**The Tricky Bit**: ACF REST API expects a specific nested structure. For Flexible Content:

```python
# Input (human-readable):
{
    "page_sections": [
        {
            "acf_fc_layout": "BasicContent",
            "heading": {
                "text": "Welcome to Single-Reel Pokies",
                "level": "h1"
            },
            "content": "<p>This is the intro paragraph...</p>"
        },
        {
            "acf_fc_layout": "GamblingOperators",
            "heading": {
                "text": "Best Casinos for Single-Reel Pokies",
                "level": "h2"
            },
            "shortcode": "[cta_list id=\"123\"]",
            "content_above": "<p>Check out these top picks...</p>"
        }
    ]
}

# Output (ACF REST API format):
{
    "acf": {
        "page_sections": [
            {
                "acf_fc_layout": "BasicContent",
                "section_id": "",
                "padding_override": "reduced-padding",
                "section_width": "narrow",
                "toc_exclude": false,
                "heading": {
                    "text": "Welcome to Single-Reel Pokies",
                    "level": "h1",
                    "alignment": {
                        "desktop": "inherit",
                        "mobile": "inherit"
                    }
                },
                "content": "<p>This is the intro paragraph...</p>"
            },
            # ... etc
        ]
    }
}
```

**Required Functions**:
```python
def transform_to_acf(content: dict, field_mapping: dict) -> dict:
    """Transform human-readable content to ACF format"""
    
def apply_defaults(section: dict, layout_fields: dict) -> dict:
    """Apply default values for optional fields"""
    
def validate_required_fields(section: dict, layout_fields: dict) -> list:
    """Return list of missing required fields"""
```

---

### 3. Content Templates (`templates/`)

**Purpose**: Define the structure LLMs should fill in.

**Base Section Template Example** (`templates/base_templates/basic_content.yaml`):
```yaml
name: BasicContent
description: A simple content section with heading and WYSIWYG content
fields:
  heading:
    text:
      type: string
      description: "The section heading text"
      llm_instruction: "Write a compelling, SEO-friendly heading"
    level:
      type: select
      options: [h1, h2, h3, h4, h5, h6]
      default: h2
      llm_instruction: "Use h1 only for main page title, h2 for major sections"
  content:
    type: html
    description: "Main content body (HTML allowed)"
    llm_instruction: |
      Write engaging, informative content. Use:
      - <p> for paragraphs
      - <ul>/<li> for lists
      - <strong> for emphasis
      - Keep paragraphs digestible (3-4 sentences max)
      Target word count: 150-300 words
  # Optional fields (not sent to LLM, use defaults)
  _defaults:
    section_id: ""
    padding_override: "reduced-padding"
    section_width: "narrow"
```

**Page Template Example** (`templates/page_templates/pokies_category.yaml`):
```yaml
name: Pokies Category Page
description: Template for category pages like "Single-Reel Pokies"
slug_pattern: "online-pokies/{category_slug}/"
post_type: post  # or 'page'

variables:
  category_name:
    description: "e.g., 'Single-Reel Pokies'"
  category_slug:
    description: "e.g., 'single-reel-pokies'"
  target_keywords:
    description: "List of SEO keywords to target"
  cta_list_id:
    description: "ID for the casino CTA list shortcode"

sections:
  - layout: BasicContent
    purpose: "Introduction to the category"
    llm_context: |
      Write an engaging introduction to {category_name}.
      Target keywords: {target_keywords}
      Tone: Informative but exciting
    fields:
      heading:
        text: "{category_name}"
        level: h1
      content: "{{LLM_GENERATE}}"

  - layout: GamblingOperators
    purpose: "Casino recommendations table"
    llm_context: |
      Write brief intro text for the casino comparison table.
      Mention why these casinos are great for {category_name}.
    fields:
      heading:
        text: "Best Online Casinos for {category_name}"
        level: h2
      shortcode: "[cta_list id=\"{cta_list_id}\"]"
      content_above: "{{LLM_GENERATE}}"
      content_below: ""

  - layout: BasicContent
    purpose: "What are X pokies explanation"
    llm_context: |
      Explain what {category_name} are.
      Cover: how they work, key features, why players enjoy them.
      Be educational but not boring.
    fields:
      heading:
        text: "What Are {category_name}?"
        level: h2
      content: "{{LLM_GENERATE}}"

  - layout: AllSlotsInterlink
    purpose: "Related slots grid"
    fields:
      heading:
        text: "Find Your Perfect {category_name.singular} Below"
        level: h2
      # This layout likely auto-populates from taxonomy

  - layout: BasicContent
    purpose: "Why choose these pokies"
    llm_context: |
      Explain the benefits/appeal of {category_name}.
      Include 3-5 compelling reasons.
      Can use bullet points.
    fields:
      heading:
        text: "Why Choose {category_name}?"
        level: h2
      content: "{{LLM_GENERATE}}"

  - layout: BasicContent
    purpose: "Closing/summary section"
    llm_context: |
      Write a brief conclusion wrapping up the page.
      Include a soft CTA encouraging exploration.
    fields:
      heading:
        text: ""  # No heading for conclusion
        level: h2
      content: "{{LLM_GENERATE}}"
```

---

### 4. LLM Content Generator (`llm/content_generator.py`)

**Purpose**: Orchestrate content generation using LLM.

**Process Flow**:
1. Load page template
2. Substitute variables
3. For each section with `{{LLM_GENERATE}}`:
   - Build context-aware prompt
   - Call LLM API
   - Validate/sanitize response
   - Insert into template
4. Return completed content structure

**System Prompt Strategy**:
```python
SYSTEM_PROMPT = """
You are a content writer for online casino/gambling websites.

TONE: Professional but approachable, informative, trustworthy.
AUDIENCE: Australian players looking for pokies/casino information.
COMPLIANCE: Never make false claims. Use phrases like "up to" for bonuses.

When writing HTML content:
- Use semantic HTML (<p>, <ul>, <strong>, <em>)
- Do NOT include <html>, <head>, <body> tags
- Do NOT use inline styles
- Keep paragraphs short (3-4 sentences)
- Use bullet points for lists of features/benefits

Respond ONLY with the requested content. No explanations or preamble.
"""
```

**Per-Section Prompting**:
```python
def generate_section_content(section_config: dict, variables: dict) -> str:
    """Generate content for a single section"""
    
    prompt = f"""
    Page Context: {variables.get('page_context', '')}
    Section Purpose: {section_config['purpose']}
    
    Instructions:
    {section_config['llm_context'].format(**variables)}
    
    Write the HTML content now:
    """
    
    response = llm_client.generate(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=1000
    )
    
    return sanitize_html(response)
```

---

### 5. WordPress Client (`wordpress/client.py`)

**Purpose**: Handle all WordPress REST API communication.

**Authentication**: Use Application Passwords (WordPress 5.6+)
```python
# In wordpress_sites.yaml:
sites:
  sunvegascasino:
    base_url: "https://www.sunvegascasino.com/wp"
    username: "api-user"
    application_password: "xxxx xxxx xxxx xxxx xxxx xxxx"
    # Note: App passwords have spaces, keep them
```

**Required Functions**:
```python
class WordPressClient:
    def __init__(self, site_config: dict):
        self.base_url = site_config['base_url']
        self.auth = (site_config['username'], site_config['application_password'])
    
    def create_post(self, data: dict) -> dict:
        """Create a new post/page"""
        # POST /wp-json/wp/v2/posts
        
    def update_post(self, post_id: int, data: dict) -> dict:
        """Update existing post/page"""
        # PUT /wp-json/wp/v2/posts/{id}
        
    def get_post(self, post_id: int) -> dict:
        """Get post with ACF fields"""
        # GET /wp-json/wp/v2/posts/{id}?_fields=id,title,slug,status,acf
        
    def upload_media(self, filepath: str, alt_text: str = "") -> dict:
        """Upload media file, return attachment ID"""
        # POST /wp-json/wp/v2/media
        
    def search_posts(self, search: str, post_type: str = "post") -> list:
        """Search for existing posts"""
```

**ACF Pro REST API Notes**:
- ACF Pro exposes fields automatically at `/wp-json/wp/v2/{post_type}/{id}`
- Fields appear in the `acf` key of the response
- When updating, send the full `acf` object

---

### 6. Flask API (`api/routes.py`)

**Endpoints**:

```python
# Health check
GET /api/health

# List available page templates
GET /api/templates
Response: [{"name": "pokies_category", "description": "...", "variables": [...]}]

# List configured WordPress sites
GET /api/sites
Response: {"sites": ["sunvegascasino", ...]}

# Preview content generation (doesn't publish)
POST /api/preview
Body: {
    "template": "pokies_category",
    "variables": {
        "category_name": "Single-Reel Pokies",
        "category_slug": "single-reel-pokies",
        "target_keywords": ["classic pokies", "3-reel slots"],
        "cta_list_id": "123"
    }
}
Response: {
    "template": "pokies_category",
    "variables": {...},
    "sections": [...],
    "acf_payload": {...},
    "warnings": [...]
}

# Generate and publish
POST /api/publish
Body: {
    "site": "sunvegascasino",
    "template": "pokies_category",
    "variables": {...},
    "post_type": "post",
    "status": "draft",
    "title": "Optional override",
    "slug": "optional-slug"
}
Response: {
    "success": true,
    "post_id": 12345,
    "link": "https://...",
    "status": "draft",
    "site": "sunvegascasino",
    "template": "pokies_category"
}

# Transform pre-generated content to ACF format (for AirOps hybrid workflow)
POST /api/transform
Headers: X-API-Key: <TRANSFORM_API_KEY>
Body: {
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
        },
        {
            "layout": "GamblingOperators",
            "heading": "Best Casinos",
            "heading_level": "h2",
            "content_above": "<p>Casino intro text</p>",
            "content_below": "",
            "shortcode": "[cta_list id=\"123\"]"
        }
    ],
    "status": "draft"
}
Response: {
    "success": true,
    "payload": {
        "title": "Single-Reel Pokies",
        "slug": "single-reel-pokies",
        "status": "draft",
        "acf": {
            "page_sections": [
                {
                    "acf_fc_layout": "BasicContent",
                    "heading": {"text": "...", "level": "h1", "alignment": {"desktop": "inherit", "mobile": "inherit"}},
                    "content": "<p>...</p>",
                    "section_id": "",
                    "padding_override": "reduced-padding",
                    ...
                }
            ]
        }
    },
    "warnings": []
}
```

#### Hybrid AirOps Workflow

The `/api/transform` endpoint enables a hybrid architecture where AirOps (corporate-approved) handles the UI and LLM content generation, while our API handles the ACF field transformation that AirOps cannot do. AirOps then publishes directly to WordPress, bypassing Cloudflare bot protection.

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

The transform endpoint:
- Requires `X-API-Key` header authentication
- Normalizes AirOps flat section format (e.g., `heading` + `heading_level`) to nested ACF format
- Uses site-specific field mappings (`config/field_mappings/{site}.json`)
- Applies all ACF defaults (padding, section_width, heading alignment, etc.)
- Returns a WordPress-ready payload without making any WordPress API calls

---

## Configuration

### Environment Variables (`.env`)
```bash
# Flask
FLASK_ENV=development
FLASK_SECRET_KEY=your-secret-key

# LLM
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# Default LLM settings
LLM_PROVIDER=anthropic  # or openai
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=2000
LLM_TEMPERATURE=0.7
```

### WordPress Sites (`config/wordpress_sites.yaml`)
```yaml
sites:
  sunvegascasino:
    base_url: "https://www.sunvegascasino.com/wp"
    username: "content-api"
    application_password: "xxxx xxxx xxxx xxxx xxxx xxxx"
    default_author_id: 5
    default_status: "draft"
    
  anothersite:
    base_url: "https://another-site.com"
    # ...
```

---

## Key Implementation Notes

### 1. Handling ACF Clone Fields

Clone fields are the trickiest part. When parsing:

```python
def resolve_clones(field: dict, all_groups: dict, depth: int = 0) -> dict:
    """
    Recursively resolve clone fields.
    
    A clone field looks like:
    {
        "type": "clone",
        "clone": ["group_611e64256f84d"]  # References another group
    }
    
    We need to:
    1. Find the referenced group(s)
    2. Pull in their fields
    3. Recursively resolve any clones within those
    4. Handle the 'prefix_name' setting (affects field name nesting)
    """
    if depth > 10:
        raise RecursionError("Clone resolution too deep - circular reference?")
    
    if field.get('type') != 'clone':
        return field
    
    resolved_fields = []
    for group_key in field.get('clone', []):
        group = all_groups.get(group_key, {})
        for sub_field in group.get('fields', []):
            resolved = resolve_clones(sub_field, all_groups, depth + 1)
            resolved_fields.append(resolved)
    
    return resolved_fields
```

### 2. Flexible Content Layout Keys

When sending to WP REST API, each row needs `acf_fc_layout` set to the layout **name** (not key):

```python
{
    "acf": {
        "page_sections": [
            {
                "acf_fc_layout": "BasicContent",  # This is the layout NAME
                # ... fields
            }
        ]
    }
}
```

### 3. WYSIWYG Field Formatting

WordPress WYSIWYG (TinyMCE) expects:
- Standard HTML tags
- No wrapping `<html>`, `<body>`
- Newlines are converted to `<br>` or `<p>` based on settings
- Images as `<img>` with WordPress attachment URLs

Sanitize LLM output:
```python
def sanitize_wysiwyg(html: str) -> str:
    """Clean HTML for WordPress WYSIWYG field"""
    import bleach
    
    allowed_tags = [
        'p', 'br', 'strong', 'em', 'b', 'i', 'u',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'a', 'img',
        'blockquote', 'pre', 'code',
        'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ]
    
    allowed_attrs = {
        'a': ['href', 'title', 'target', 'rel'],
        'img': ['src', 'alt', 'width', 'height'],
        '*': ['class']
    }
    
    return bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
```

### 4. Error Handling Strategy

```python
class ContentAutomationError(Exception):
    """Base exception"""
    pass

class ACFParsingError(ContentAutomationError):
    """Failed to parse ACF export"""
    pass

class TemplateError(ContentAutomationError):
    """Invalid or missing template"""
    pass

class LLMGenerationError(ContentAutomationError):
    """LLM failed to generate content"""
    pass

class WordPressAPIError(ContentAutomationError):
    """WordPress API request failed"""
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
```

---

## Testing Strategy

### Unit Tests
- ACF parser correctly resolves clone fields
- Transformer produces valid ACF structure
- Template variables are substituted correctly

### Integration Tests
- Full flow: template → LLM → transform → WP API (use staging site)
- Media upload works
- Post creation and update work

### Mock LLM for Tests
```python
class MockLLMClient:
    def generate(self, system, prompt, **kwargs):
        return "<p>This is mock generated content for testing.</p>"
```

---

## Future Enhancements

1. **Web UI**: Simple React frontend for non-technical users
2. **Bulk Generation**: CSV upload → generate multiple pages
3. **Content Scheduling**: Queue posts for future publication
4. **SEO Integration**: Auto-generate meta descriptions, schema markup
5. **Image Generation**: DALL-E/Midjourney integration for featured images
6. **Revision Tracking**: Store content versions
7. **A/B Testing**: Generate multiple versions, track performance
8. **Multi-language**: Generate content in multiple languages

---

## Getting Started

### Prerequisites
- Python 3.11+
- WordPress site with:
  - ACF Pro installed
  - REST API enabled
  - Application Password created for API user
- Anthropic API key (or OpenAI)

### Installation
```bash
git clone <repo>
cd wp-content-automation
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### First Run
```bash
# 1. Parse your ACF export
flask parse-acf /path/to/acf-export.json --output config/field_mappings/mysite.json

# 2. Create a page template
# Edit templates/page_templates/my_template.yaml

# 3. Test generation (preview only)
flask preview --template my_template --vars '{"name": "Test"}'

# 4. Publish to WordPress
flask publish --site mysite --template my_template --vars '{"name": "Test"}' --status draft
```

---

## Appendix: Discovered Field Structure

From the provided ACF export, here are the key Page Sections layouts:

| Layout Name | Key Fields |
|------------|-----------|
| BasicContent | heading (text, level, alignment), content (wysiwyg) |
| GamblingOperators | heading, shortcode, table_appearance, content_above, content_below, call_to_action |
| AccordionSection | heading, accordion items (repeater) |
| AllSlotsInterlink | heading, taxonomy filters |
| AllReviewsInterlink | heading, review filters |
| BlacklistedCasinos | heading, summary |
| CasinoCompare | heading, casino selections |
| AuthorsGrid | heading, author selections |

All layouts share **Common Fields**:
- section_id (text)
- padding_override (select)
- section_width (select)
- toc_exclude (boolean)

---

## Questions for Implementation

1. **Authentication**: Does the WP site have Application Passwords enabled, or do we need JWT/OAuth?
2. **Post Type**: Are we targeting `post`, `page`, or a custom post type?
3. **Categories/Tags**: Should the system assign taxonomies automatically?
4. **Featured Images**: Do we need to handle featured image generation/upload?
5. **Yoast/SEO**: Should we populate SEO meta fields?
6. **Shortcode IDs**: How do we determine which CTA list shortcodes to use?

---

*Spec Version: 1.0*
*Last Updated: 2026-02-13*
