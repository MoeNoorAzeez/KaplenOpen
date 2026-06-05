# Curriculum Spec

Kaplen's curriculum system is entirely data-driven. All domain knowledge lives in `curricula/registry.json` and JSON content files in S3. No code changes are required to add or modify a curriculum.

---

## Registry file

`curricula/registry.json` is an array of curriculum objects loaded at startup.

### Top-level schema

```json
{
  "id": "string (unique slug)",
  "name": "string (display name)",
  "levels": ["array", "of", "level", "names"],
  "path_template": "s3/path/template/{level1}/{level2}.json",
  "s3_bucket_env": "ENV_VAR_NAME_holding_bucket",
  "quality_rules": { ... },
  "title_patterns": { ... },
  "hook_archetypes": ["array"],
  "generation_hints": { ... }
}
```

### Fields

#### `id` (required)
Unique slug used in API calls. Example: `"iraqi-moe-2024"`, `"us-k12-stem"`.

#### `name` (required)
Human-readable display name shown in `/api/curricula`.

#### `levels` (required)
Ordered array of hierarchy level names, from broadest to most specific. These become the keys in `path_template` and the `path_args` parameter in API calls.

Examples:
```json
["subject", "topic", "subtopic"]
["grade", "subject", "unit", "lesson"]
["course", "module", "chapter"]
```

#### `path_template` (required)
S3 object key template. Use `{level_name}` placeholders matching your `levels` array.

Examples:
```json
"subtopics/{subject}/{topic}/{subtopic}.json"
"content/{grade}/{subject}/{unit}/{lesson}.json"
```

The loader calls `path_template.format(**path_args)` to build the S3 key.

#### `s3_bucket_env` (required)
Name of the environment variable that holds the S3 bucket name. Typically `"S3_BUCKET"`.

#### `quality_rules` (optional)
Controls how `ContentValidator` scores generated content.

```json
{
  "min_coverage_percent": 70,
  "required_dimensions": ["concepts", "examples", "practice_problems"],
  "scoring_weights": {
    "concepts": 0.4,
    "examples": 0.3,
    "practice_problems": 0.3
  }
}
```

| Field | Default | Description |
|---|---|---|
| `min_coverage_percent` | 70 | Minimum score to pass validation |
| `required_dimensions` | `["concepts","examples","practice"]` | Content fields the validator checks |
| `scoring_weights` | equal weights | Per-dimension weight (must sum to 1.0) |

#### `title_patterns` (optional)
Hints for `YoutubePackager` when generating video titles.

```json
{
  "prefix": "شرح",
  "style": "question"
}
```

#### `hook_archetypes` (optional)
List of hook styles the packager may use. If omitted, all archetypes are available.

```json
["teacher", "relatable", "question", "story", "surprising", "problem"]
```

#### `generation_hints` (optional)
Free-form dict passed to generators for prompt customisation.

```json
{
  "language": "Arabic",
  "audience": "high school students",
  "tone": "conversational"
}
```

---

## S3 content files

Each leaf node in the curriculum hierarchy is a JSON file in S3. The path is built from `path_template` + the `path_args` supplied by the API caller.

### Minimum required fields

```json
{
  "title": "Lesson or subtopic title"
}
```

### Full example

```json
{
  "title": "Newton's Second Law",
  "objectives": [
    "Understand the relationship between force, mass, and acceleration",
    "Apply F = ma to solve problems"
  ],
  "concepts": [
    "Net force",
    "Mass vs weight",
    "Acceleration direction"
  ],
  "examples": [
    "A 2 kg block pushed with 10 N accelerates at 5 m/s²",
    "Heavier objects need more force for the same acceleration"
  ],
  "practice_problems": [
    "A 5 kg object accelerates at 3 m/s². What is the net force?",
    "If force doubles and mass stays the same, what happens to acceleration?"
  ],
  "notes": "Students often confuse mass and weight — emphasise the distinction early."
}
```

Any fields beyond `title` can be named freely. The names must match the `required_dimensions` in `quality_rules` for the validator to check them.

---

## API usage

### List curricula
```
GET /api/curricula
```

### Get curriculum details
```
GET /api/curricula/{id}
```

### Navigate hierarchy
```
GET /api/curricula/{id}/hierarchy/{level}
GET /api/curricula/{id}/hierarchy/{level}/{item}/children
```

### Generate content with a curriculum
```
POST /api/generate
{
  "curriculum_id": "my-curriculum",
  "path_args": {
    "grade": "10",
    "subject": "physics",
    "unit": "mechanics",
    "lesson": "newtons-second-law"
  },
  "hook_archetype": "question",
  "duration_minutes": 12
}
```

---

## Bundled curricula

### `iraqi-moe-2024`

Iraqi Ministry of Education 2024 syllabus. Three levels: `subject → topic → subtopic`.

- Path template: `subtopics/{subject}/{topic}/{subtopic}.json`
- Languages: Arabic (primary)
- Hook archetypes: teacher, relatable, question, story, surprising, problem

### `us-k12-stem`

US K-12 STEM example (ships as a template — S3 content not included). Four levels: `grade → subject → unit → lesson`.

---

## Adding a curriculum: checklist

- [ ] Add entry to `curricula/registry.json`
- [ ] Upload content JSON files to S3 under the matching path template
- [ ] Set `S3_BUCKET` env var (or a custom `s3_bucket_env`) to point at the correct bucket
- [ ] Test with `GET /api/curricula/{id}` — should return your entry
- [ ] Test generation with `POST /api/generate` passing `curriculum_id` and `path_args`
