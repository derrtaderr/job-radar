---
description: Register a custom Typst resume or cover-letter template so /apply can use it. Refuses to register anything that does not compile.
argument-hint: <path to a .typ file> (optional — the command will ask if omitted)
---

# /add-template

Register a Typst template with `templates/registry.yaml` so `/apply` can draft into it.

The stock templates work, but a resume layout is personal. Someone who already has a Typst
resume they like should be able to keep it and still get the drafting, verification, and ATS
machinery around it.

**Every command in this file runs from the repo root, using `.venv/bin/python`.** Paths are
repo-relative throughout, and the registry loader resolves `source:` against the repo root.

The rule that shapes this whole command: **a template gets registered only after it has
compiled in front of you.** A registry entry is a promise that `/apply` can produce a PDF
from that source. Registering an unverified file breaks the promise at the worst moment —
mid-application, with the human waiting — so the compile happens first, every time.

---

## Step 1 — Interview

`$ARGUMENTS` may hold the source path. Ask for whatever is missing, and confirm what was
given rather than assuming:

1. **Source file** — the path to the `.typ` file. It must exist and it must be Typst.
2. **Kind** — `resume` or `cover`. Those are the only two the registry knows
   (`KNOWN_KINDS` in `engine/draft/registry.py`), and a third value is rejected at load
   time. The kind decides which default `/apply` reaches for.
3. **Compile expectations** — does it compile standalone today? Does it pull in fonts,
   images, or `#import`ed files? A template that depends on a font the machine doesn't have
   still compiles, but with substituted metrics and a different page count, which is the
   kind of surprise that shows up as an overflow three steps later. Ask now.
4. **Page limit** — the hard ceiling `/apply` verifies against, as an integer. Two for a
   resume and one for a cover letter are the usual answers. This is a budget the drafter
   cuts content to fit, not a description of how long the template currently runs.
5. **Name** — the registry key, e.g. `my-resume`. Lowercase with hyphens, and unique;
   a duplicate name raises `RegistryError` at load time.
6. **Default?** — should this become `default_resume` / `default_cover`, the template
   `/apply` picks with no argument? Ask explicitly. Changing a default silently changes
   every future application.

Also read the source before going further and check it for the content marker:

```
// ===== CONTENT START — the /apply drafter edits ONLY below this line =====
```

`/apply` edits only below that line and leaves everything above it alone. A template without
the marker will still compile and still register, but the drafter has no boundary to respect
in it — so say so, and offer to add the marker at the point where layout ends and content
begins. Adding it is a one-line change to a copy and it is what makes the template safe to
draft into repeatedly.

## Step 2 — Copy into templates/custom/

```bash
mkdir -p templates/custom
cp <source path> templates/custom/<file>.typ
```

Copy, never register a path outside the repo. A registry entry pointing at a file somewhere
in the home directory breaks the moment that file moves, and `load_registry` raises on a
missing source — loudly, but during an application.

**`templates/custom/` is gitignored, and that is deliberate.** A personal resume template
usually carries the header content baked in — real name, real email, real phone, sometimes a
full work history. That is personal data, and this repo's standing rule is that personal data
lives in gitignored paths only (`config/`, `apply-out/`, `templates/custom/`). The privacy
guard fails a commit that carries an email or phone number in a tracked file, so a template
copied into a tracked directory would block the next commit anyway. Tell the human this, once
— it is the reason their template is not going to show up in `git status`, and unexplained
silence there reads like a bug.

## Step 3 — Test compile (mandatory, before the registry is touched)

Compile the copy in `templates/custom/`, writing the PDF to a throwaway path so the repo
doesn't accumulate build artifacts next to sources:

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.draft.compile import compile_pdf
ok, log = compile_pdf(Path('templates/custom/<file>.typ'), Path('/tmp/tmpl-test.pdf'))
print('OK' if ok else 'FAIL')
print(log)
"
```

`compile_pdf` returns `(ok, log)` and does not raise on a broken document — the log is the
Typst error output, and it names the line. It raises `FileNotFoundError` only when the
`typst` binary is missing, which means `brew install typst` and is an environment problem,
not a template problem.

**If this compile fails, stop. Do not write the registry entry.** Report the Typst error,
offer to fix it in `templates/custom/<file>.typ`, and re-run this step. Registering a
template that does not compile means `/apply` fails mid-draft on a document the human
believed was ready — the failure this command exists to make impossible. There is no flag,
no override, and no "register it for now."

The page count gets checked mechanically in Step 5, once the registry knows the limit.

## Step 4 — Append the registry entry

Only now, with a green compile behind it, edit `templates/registry.yaml` and append to
`templates:`:

```yaml
  - {name: <name>, source: templates/custom/<file>.typ, kind: <resume|cover>, page_limit: <N>}
```

`source` is repo-relative — `load_registry` resolves it against the repo root. `page_limit`
must be a bare integer; the loader rejects `2.0` and rejects `yes` (which YAML would
otherwise hand back as `True`, and `True` passes an int check).

If this template is becoming the default, update the matching top-level key in the same
edit:

```yaml
default_resume: <name>
```

### This edit crosses the tracked/gitignored line — say so out loud

`templates/registry.yaml` is a **tracked** file. `templates/custom/` is **gitignored**. So a
custom registration is the one place in this repo where a tracked file points at a source
git will never carry, and the human needs to know that before they commit anything:

- `git status` will show `templates/registry.yaml` as modified. That is expected, not a bug.
- **Committing an entry whose source lives in `templates/custom/` breaks every fresh clone.**
  `load_registry` raises `RegistryError` on a source that does not exist, so the next person
  to clone the repo — or the same person on a second machine — gets a hard failure on every
  registry load, including `/apply`'s first step.
- The registry edit is therefore the human's to keep local or to commit knowingly. Keeping
  it local is the normal choice for a personal template, the same way `config/` stays local.
  Committing it only makes sense if the source is also tracked — a template with no personal
  data, living in `templates/` rather than `templates/custom/`.

State which of those two this is when reporting in Step 6. Do not commit the registry edit
on the human's behalf.

## Step 5 — Verification compile of the registered entry

Step 3 proved the file compiles. This step proves the **registry** is right about it — that
the name resolves, the source path as written in the YAML points at the file, the kind is
what was intended, and the page limit is what will be enforced. Those are different claims
from "the file compiles," and a typo'd `source:` passes the first and fails the second.

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.draft.registry import load_registry
from engine.draft.compile import compile_pdf
registry = load_registry(Path('.'))
template = registry.get('<name>')
print(template.name, template.kind, template.page_limit, template.source)
ok, log = compile_pdf(template.source, Path('/tmp/tmpl-registered.pdf'))
print('OK' if ok else 'FAIL')
print(log)
"
```

Then check the compiled PDF against the page limit the registry now enforces, with the same
tool `/apply` will use — not by opening it and eyeballing:

```bash
.venv/bin/python tools/verify_pdf.py /tmp/tmpl-registered.pdf --max-pages <N>
```

Exit 0 prints `verify_pdf: OK (N pages)`. Read the two possible failures differently:

- **`N pages > max N` is a real finding.** An unfilled template that already exceeds its own
  limit is a budget the drafter can never hit. Raise the limit or tighten the layout, and
  re-run.
- **`text layer nearly empty` here is usually expected, not a failure.** The check fires
  under 200 extracted characters, and a skeleton template is mostly placeholders — the stock
  resume compiles to 215 characters unfilled, barely over the line, so a sparser template
  will trip it for no bad reason. It only matters if the template carries plenty of visible
  placeholder text and still reports near-empty, which means the text isn't extractable at
  all (an image-based layout, or a font that doesn't export text). That would make every
  resume drafted from it unreadable to an ATS, and it needs fixing before the template is
  used for anything real.

If the template was made a default, confirm that too:

```bash
.venv/bin/python -c "
from pathlib import Path
from engine.draft.registry import load_registry
print(load_registry(Path('.')).default('<resume|cover>').name)
"
```

**A failure here means the entry comes back out.** `RegistryError` naming a missing source
or a bad field is a typo in the YAML — fix it and re-run. A compile that passed in Step 3
and fails here is pointing at the wrong file. Either way the registry does not stay in a
state where `/apply` would pick up something broken.

## Step 6 — Report

Say what landed:

- The copied source path, and that `templates/custom/` is gitignored and why.
- The registry line as written.
- **The tracked/gitignored call** — that `templates/registry.yaml` now shows as modified in
  `git status`, and whether this entry should stay local (the normal case for a personal
  template with a gitignored source) or is safe to commit (only when the source is tracked
  too). Committing an entry that points into `templates/custom/` breaks every fresh clone.
- Both compile results — the pre-registration test and the post-registration verification,
  plus the `verify_pdf` page-count result.
- Whether the default changed, and for which kind.
- How to use it: `/apply` takes the defaults automatically; a non-default template is
  selected by name through the registry (`registry.get('<name>')`).
- If the template has no content marker and the offer to add one was declined, repeat that
  once here. It is the thing that will bite during the first draft.
