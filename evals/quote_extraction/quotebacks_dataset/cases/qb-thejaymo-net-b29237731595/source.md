# Raindrop.io Stella Prompts for Organising Bookmarks - thejaymo.net

[Raindrop.io](https://raindrop.io/) recently released [*Stella*](https://help.raindrop.io/stella), an AI assistant for searching, organising, and summarising bookmarks. I’ve been using it to work through nearly 18 years of saved links, and the experience of chatting with my bookmark archive has been surprisingly great. In some situations, it has even replaced mindless doomscrolling, especially in the little moments like waiting in a supermarket queue.

At first I was using Stella for simple library maintenance; cleaning up duplicate tags, fixing spelling mistakes, merging related tags, and dealing with the sheer inertia of a tag collection that has been accreting since *del.icio.us*. Lately, though, I’ve been getting more ambitious: processing my read-but-unsorted bookmarks and moving the good ones into my public feed at [links.thejaymo.net.](http://links.thejaymo.net/)

After a lot of trial and error with batch processing, I realised the best approach was to call [Raindrop’s MCP tool names](https://help.raindrop.io/integrations/mcp#available-tools) directly using the public API documentation.

So below I’m sharing two versions of the prompt I ended up with. This prompt uses my own Raindrop setup, including collection names like `thejaymo`, my preferred bookmark note style, and the rules I use for deciding what goes into my [public links feed](https://links.thejaymo.net/). You’ll need to swap in your own collection names, tag, and review criteria before using it yourself.

Both process five oldest bookmarks at a time, stage the proposed changes for review, and let you confirm everything before updating your library. One is a heavier, more explicit prompt with plenty of guard rails; the other is a shorter, lighter version that is less prescriptive.

If you found this page looking for a Raindrop.io Stella prompt, an MCP example, or a better workflow for organising bookmarks, this should be a useful place to start.

## Heavy Prompt

**UPDATE – 26 April 26:** Update to specify [API feature names](https://developer.raindrop.io/v1/raindrops) in addition to the MCP tool calling, to make the prompt more reliable and robust.  
**UPDATE – 7 May 26:** Update to Phase 5+6 to make appearance of user facing `Approve` button in the app UI more reliable in certain circumstances.  
**UPDATE – 20 May 26:** Removes Phase 6. Phase 5 updated to instruct Stella to process prepared bookmarks sequentially rather than update in a single payload. Improves `updating bookmarks` reliability.   
**UPDATE – 20 Jul 26:** I think Raindrop MCP changed and broke tag updating. Implemented nested updates: `bookmark_ids` → `update schema`, with `add_tags` and `collection_id`. After fighting Stella for information about `generic tool-update_bookmarks: Unknown error`. **-V6**

stella-heavy-thejaymo-v6

Copy

```
# Stella Bookmark Workflow

Use the Raindrop MCP tools to process the five oldest bookmarks in Unsorted. Analyse each bookmark, show one combined preview, and make no changes until I explicitly confirm.

## Tools

Use only:

* `find_bookmarks`

* `fetch_bookmark_content`

* `find_tags`

* `find_collections`

* `update_bookmarks`

## Constraints

* Do not call `update_bookmarks` before confirmation.

* Fetch and finish one bookmark before fetching the next.

* Do not fetch all bookmark contents upfront.

* Treat the discovered bookmarks as a fixed working set.

* Preserve discovery order throughout.

* Never mix content, notes, tags, titles, URLs, or decisions between bookmarks.

* Titles must come from bookmark metadata, not fetched content.

* Never add quotation marks around extracted passages.

* Flagged changes require separate confirmation by bookmark number and item.

Maintain:

* `working_set`

* `tag_vocabulary`

* `target_collection`

* `proposals`

* `skipped`

* `flagged`

Keep stored values structured. Preview formatting must never replace internal values.

## Phase 1: Working set

Call `find_bookmarks` once with:

* `collectionId: -1`

* `sort: created`

* `perpage: 5`

* `page: 0`

This means Unsorted, oldest first, five results.

Store the returned bookmarks as immutable `working_set`, preserving returned order. If fewer than five are returned, use those.

Retain for each bookmark:

* index

* bookmark ID

* title

* URL

* existing note

* existing tags

* current collection

## Phase 2: Preflight

Before fetching content:

1. Call `find_tags` once for the existing tag vocabulary.

2. Call `find_collections` once to locate `thejaymo` and record its `_id`.

If `thejaymo` is not found, continue analysis but set:

`Collection action: ⚠️ Flagged for review — collection thejaymo was not found`

Do not create a collection.

Use existing tags wherever possible. Use a targeted `find_tags` search only when unsure whether a concrete subject tag exists.

## Phase 3: Analyse sequentially

Process bookmarks in `working_set` order.

For each bookmark:

1. Reset all temporary variables.

2. Fetch only that bookmark’s content.

3. Read only that content.

4. Extract one key passage.

5. Prepare the exact note update.

6. Propose the final tag set.

7. Decide the collection action.

8. Store the proposal.

9. Continue to the next bookmark.

Each proposal must contain:

* `index`

* `bookmark_id`

* `title`

* `url`

* `key_passage`

* `note_field_preview`

* `existing_tags`

* `proposed_tags`

* `collection_action`

* `flagged_items`

`proposed_tags` must always be an array of plain strings without `#` prefixes or review annotations.

## Key passage

Extract exactly one passage per bookmark.

It must:

* be contiguous source text from that bookmark

* preserve exact wording

* contain no more than 100 words

* preferably be a complete paragraph

* contain no quotation marks added by you

Prefer:

1. counter-intuitive beat

2. thesis sentence or paragraph

3. strong statistic

4. buried irony

If no usable passage exists:

`Key passage: ⚠️ No usable passage found — [reason]`

Do not invent or substitute content.

## Notes

When a usable passage exists:

* place it at the top

* preserve it exactly

* do not wrap it in quotation marks

* if the existing note is empty, use only the passage

* otherwise use the passage, one blank line, then the existing note unchanged

If no passage exists, use a subtitle only when clearly appropriate. Otherwise preserve the existing note and flag the note update.

## Tags

Ask what the bookmark is materially about.

Choose three to seven final tags in this order:

1. concrete subject

2. close subject

3. broader subject

4. lens or context

Use existing tags wherever suitable. Precise subject tags beat broad or high-count tags.

`proposed_tags` is the complete desired tag list. Preserve existing tags that remain appropriate. Remove one only when clearly irrelevant, mistaken, or superseded. Proposed tags are tags to add; store them as an array of plain strings and preserve existing tags.

All tag values must:

* be plain strings

* contain no leading `#`

* be lowercase and hyphenated where appropriate

* contain no warning or review text

* be deduplicated

Only propose a new tag when no suitable existing tag exists. Store the plain tag normally and record the review requirement separately in `flagged_items`.

## Collections

Default:

`Collection action: Move to thejaymo`

Flag the move if the bookmark is:

* highly personal or private

* sensitive

* paywalled with no usable excerpt

* too time-sensitive to age well

* unsuitable for public curation

Use:

`Collection action: ⚠️ Flagged for review — [reason]`

Proposed tags are tags to add; store them as an array of plain strings and preserve existing tags.

## Phase 4: Preview

After all proposals are stored, show one combined preview. Do not call `update_bookmarks`.

Use:

### Bookmark [n]

Title: [exact title from working_set]

Key passage: [exact passage, maximum 100 words]

Tags: #tag1 #tag2 #tag3

Note field preview: [exact note value]

Collection action: [Move to thejaymo or flagged action]

The `Tags:` line is display-only formatting derived from `proposed_tags`. Never use or parse it as update input.

For new tags, also show:

`New tag requiring confirmation: #tag`

If the title is missing:

`Title: ⚠️ Missing bookmark title — [URL or bookmark ID]`

After all bookmarks, output exactly:

`Confirm? Reply yes all to apply everything, no all to cancel, skip [n] to exclude a bookmark, or [n] edit [change] to amend a specific bookmark.`

## Phase 5 — Confirmation and apply

Valid commands only: `yes all`, `no all`, `skip [n]`, `[n] edit [change]`,

`yes all + [n] [change]`. Treat ambiguous replies such as `yes`, `looks good`,

`go ahead`, or `do it` as invalid.

Applying means calling `update_bookmarks`. On an apply command, make the first

tool call before any prose.

* `yes all`: apply proposals one bookmark at a time, in `working_set` order.

* `no all`: change nothing and call nothing.

* `skip [n]`: exclude bookmark `n` and reshow the preview.

* `[n] edit [change]`: revise only bookmark `n` and reshow the preview.

* `yes all + [n] [change]`: amend bookmark `n`, then apply as `yes all`.

`yes all` excludes flagged collection actions, flagged note updates, and

unconfirmed new tags.

For each approved bookmark, call `update_bookmarks` using exactly:

```json

{

"updates": [

{

"bookmark_ids": [BOOKMARK_ID],

"update": {

"note": "APPROVED NOTE",

"add_tags": ["tag1", "tag2"],

"collection_id": TARGET_COLLECTION_ID

}

}

]

}

```

Include only fields that have an approved change.

Rules:

* `bookmark_ids` must be an array containing the current bookmark ID.

* Tags must use `add_tags`, not `tags`.

* `add_tags` must be an array of plain strings without `#` prefixes.

* The collection must use `collection_id`.

* Build values from the stored proposal, never from the formatted preview.

* Existing tags remain; `add_tags` appends the approved proposed tags.

* Never combine `add_tags` and `remove_tags` in one update operation.

* If tag removal is explicitly approved, call `remove_tags` separately and

wait for its result before calling `add_tags`.

* Wait for each bookmark’s result before updating the next bookmark.

* After the last call, report note, tag, and collection results separately.

## Applying updates

Process one bookmark at a time in `working_set` order. Finish all operations for that bookmark before continuing.

Build every update from the stored proposal, never from the displayed preview.

Use the live `update_bookmarks` schema exactly as exposed by the MCP tool. Do not assume its field names match the REST API.

For tags:

* use the live schema’s tag argument

* pass an array of plain strings

* never pass hashtags or comma-separated text

* if the tool supports full replacement, pass `proposed_tags`

* if it instead supports separate add/remove operations, derive and apply them from `existing_tags` and `proposed_tags`

Never combine a tag operation with a collection move in the same `update_bookmarks` call.

For each bookmark, apply sequentially:

1. note update, if needed

2. tag removal, if needed and supported

3. tag addition or full replacement, if needed

4. collection move, if confirmed

Wait for each result before making the next call. Never make simultaneous update calls.

Before each call, verify:

* bookmark ID is present

* tag values are arrays of plain strings

* no tag begins with `#`

* no tag contains warning text

* note text matches `note_field_preview`

* collection uses the verified `thejaymo` ID

* the call changes only the intended bookmark and field group

Inspect every tool result. Report note, tags, and collection separately. Do not report the whole bookmark as successfully updated merely because one operation succeeded.

If a tag result exposes the resulting tags and they do not match the intended change, stop before moving the bookmark or processing the next one and report the mismatch.

If the result does not expose tags, report:

`Tags: update requested; the tool result did not provide enough data to verify`
```

## Shorter Prompt

stella-thejaymo-quickstart

Copy

```
# Stella Bookmark Workflow Prompt

Use the MCP bookmark tools to complete this workflow from discovery through preview. Do not apply changes until I explicitly confirm.

## Objective

Find the 5 oldest bookmarks in my Raindrop Unsorted collection. Treat those bookmarks as the fixed working set for this run. Analyse each bookmark individually, propose note, tag, and collection updates, then show one combined preview and wait for confirmation.

## Tools

Use only:

- `find_bookmarks`

- `fetch_bookmark_content`

- `find_tags`

- `find_collections`

- `update_bookmarks`

## Hard constraints

- Do not call `update_bookmarks` before explicit confirmation.

- Do not fetch content for more than one bookmark at a time.

- Do not fetch all bookmark contents up front.

- Do not add, replace, reorder, or mutate bookmarks in the working set unless I explicitly ask.

- Preserve discovery order through preview and update.

- Treat each bookmark as a sealed unit: do not compare bookmarks or mix passages, notes, tags, titles, URLs, or collection decisions across bookmarks.

- Never add quotation marks around extracted passages.

- Flagged changes require explicit confirmation by bookmark number and item.

## Internal state

Maintain:

- `working_set`: fixed bookmarks from Phase 1

- `tag_vocabulary`: existing tags from `find_tags`

- `target_collection`: verified `thejaymo` collection and its `_id`

- `proposals`: one stored proposal per bookmark

- `skipped`: bookmark indexes excluded by user

- `flagged`: proposed changes requiring explicit confirmation

Do not mutate `working_set`.

## Phase 1 — Establish working set

Call `find_bookmarks` once using Raindrop API semantics:

- `collectionId: -1`

- `sort: created`

- `perpage: 5`

- `page: 0`

This means:

- `collectionId: -1` = system Unsorted collection

- `sort: created` = created date ascending / oldest first

- `perpage: 5` = return 5 bookmarks

Do not use `collection: unsorted`, `limit`, or `sort: oldest first` unless the tool explicitly maps those aliases to the Raindrop fields above.

Store the returned bookmarks as immutable `working_set`, preserving returned order. If fewer than 5 are returned, use only those.

Each item must retain:

- index number

- bookmark id

- title

- URL, if available

- existing note, if available

- current tags, if available

- current collection, if available

Titles in previews must come from `working_set` metadata, not fetched page content.

## Phase 2 — Preflight vocabulary

Before analysing content:

1. Call `find_tags` once for the existing tag vocabulary.

2. Call `find_collections` once to verify `thejaymo` exists and record its `_id`.

If `thejaymo` does not exist, continue analysing but mark every collection action as:

`Collection action: ⚠️ Flagged for review — collection thejaymo was not found`

Do not create collections unless I explicitly ask.

During analysis, use existing tags wherever possible. If unsure whether a subject tag exists, call `find_tags` with a targeted query for that bookmark’s concrete subject.

## Phase 3 — Analyse bookmarks sequentially

Process bookmarks in `working_set` order.

For each bookmark, finish all steps before fetching the next bookmark:

1. Reset temporary passage, note, tag, collection, and flag variables.

2. Call `fetch_bookmark_content` for this bookmark only.

3. Read only this bookmark’s content.

4. Extract one key passage.

5. Prepare the note field preview.

6. Propose 3 to 7 tags.

7. Decide the collection action.

8. Store the proposal keyed by bookmark index.

9. Move to the next bookmark.

Each proposal must include:

- `index`

- `bookmark_id`

- `title`

- `url`

- `key_passage`

- `note_field_preview`

- `proposed_tags`

- `collection_action`

- `flagged_items`

## Key passage rules

Extract exactly one key passage per bookmark.

The passage must:

- be contiguous text from that bookmark only

- preserve exact wording

- be no more than 100 words

- preferably be a full paragraph

- contain no quotation marks added by you

- remove leading or trailing quote/block formatting only if it is source formatting

Prefer the strongest buried passage over the obvious lede, in this order:

1. counter-intuitive beat

2. thesis sentence or paragraph

3. sharp statistic or data anchor

4. buried irony

If no usable passage exists, set:

`Key passage: ⚠️ No usable passage found — [reason]`

Do not invent or substitute content.

## Note rules

Prepare the note update for the current bookmark only.

If a key passage exists:

- put the passage at the top

- do not paraphrase it

- do not wrap it in quotation marks

- if the existing note is empty, the new note is just the passage

- if the existing note contains text, prepend the passage, then one blank line, then preserve the existing note exactly

If no usable passage exists, use an article subtitle only if appropriate; otherwise leave the existing note unchanged and flag the note update.

Do not write the note update until confirmation.

## Tag rules

Ask: what is this bookmark materially about?

Propose 3 to 7 tags in this priority order:

1. concrete subject

2. close subject

3. broader subject

4. lens/context

Use existing tags wherever possible. Precise subject tags beat loose general tags, even if the precise tag has lower usage. High-count tags are tie-breakers, not replacements for the subject.

Do not omit the concrete subject in favour of abstract tags.

Only propose a new tag if no suitable existing tag exists. Mark it:

`#new-tag ⚠️ new tag for review`

Use lowercase, hyphenated style where appropriate.

## Collection rules

Default:

`Collection action: Move to thejaymo`

When applying this move, use the verified `thejaymo` collection `_id` as:

`collection: { "$id": target_collection._id }`

Flag the collection action instead if the bookmark is:

- highly personal or private

- sensitive

- paywalled with no usable excerpt

- too time-sensitive to age well

- unsuitable for public curation for any clear reason

Use:

`Collection action: ⚠️ Flagged for review — [reason]`

## Phase 4 — Combined preview

After all proposals are stored, show one combined preview.

Do not apply changes yet.

Do not call `update_bookmarks` yet.

Use this exact format for each bookmark:

### Bookmark [n]

Title: [title copied exactly from working_set]

Key passage: [exact passage, maximum 100 words, no quotation marks]

Tags: #tag1 #tag2 #tag3

Note field preview: [exact text that will be written to the note field]

Collection action: [Move to thejaymo OR flagged action]

If title is missing, use:

`Title: ⚠️ Missing bookmark title — [URL or bookmark id]`

After all preview blocks, output exactly:

`Confirm? Reply [y] yes all to apply everything, no all to cancel, skip [n] to exclude a bookmark, or [n] edit [change] to amend a specific bookmark.`

## Phase 5 — Confirmation

Only these commands are valid:

- `[y] yes all`

- `no all`

- `skip [n]`

- `[n] edit [change]`

- `yes all + [n] [change]`

Ambiguous replies such as `yes`, `looks good`, `go ahead`, `update them`, or `do it` must not trigger updates.

Behaviour:

- `[y] yes all`: apply all approved, unskipped, unflagged proposals

- `no all`: cancel without changing anything

- `skip [n]`: exclude that bookmark, then show the updated combined preview

- `[n] edit [change]`: revise only that bookmark’s stored proposal, then show the combined preview again

- `yes all + [n] [change]`: apply all approved, unskipped, unflagged proposals, including the stated amendment to bookmark `n`

`yes all` does not approve flagged collection actions, flagged note updates, or new tags. Flagged items require explicit confirmation by bookmark number and item.

## Phase 6 — Apply approved changes

Only after valid confirmation, call `update_bookmarks`.

For each approved bookmark, apply only its approved changes:

- update the note field with that bookmark’s approved note text

- update tags with that bookmark’s approved tags

- move it to `thejaymo` only if approved

Do not update skipped bookmarks.

Do not apply unconfirmed flagged changes.

Do not modify anything outside the fixed working set.

If notes or tag sets differ, update bookmarks separately or group only bookmarks whose approved payloads are exactly identical.

After applying changes, return a concise summary of updated, skipped, and still-flagged bookmarks.
```
