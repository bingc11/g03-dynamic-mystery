"""Validate packaged case data before the dialogue engine uses its references."""

import re


CASE_ID = re.compile(r"[a-zA-Z0-9_-]+")


def _mapping(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected nonempty text")


def _items(value, path, *, minimum=0):
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{path}: expected a list with at least {minimum} items")
    for item in value:
        _text(item, path)
    if len(set(value)) != len(value):
        raise ValueError(f"{path}: repeated value")
    return value


def _reference(value, allowed, path):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{path}: unknown reference {value!r}")


def _references(value, allowed, path, *, minimum=0):
    for item in _items(value, path, minimum=minimum):
        _reference(item, allowed, path)


def _boolean(item, key, path):
    if key in item and type(item[key]) is not bool:
        raise ValueError(f"{path}.{key}: expected a boolean")


def validate_case(case, expected_id=None):
    """Return the case unchanged, or reject invalid cross-references and answer keys."""
    case = _mapping(case, "case")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
        raise ValueError("case.id: expected a letter, number, hyphen or underscore identifier")
    if expected_id is not None and case_id != expected_id:
        raise ValueError(f"case.id: expected {expected_id!r}")
    _text(case.get("title"), "case.title")
    roles = _mapping(case.get("roles"), "roles")
    evidence = _mapping(case.get("evidence"), "evidence")
    topics = _mapping(case.get("topics"), "topics")
    records = _mapping(case.get("records"), "records")
    actions = _mapping(case.get("actions"), "actions")
    if len(set(evidence) | set(topics) | set(records)) != len(evidence) + len(topics) + len(records):
        raise ValueError("evidence, topics and records must have distinct IDs")

    verdict = _mapping(case.get("verdict"), "verdict")
    _references(verdict.get("suspects"), roles, "verdict.suspects", minimum=2)
    motives = _items(verdict.get("motives"), "verdict.motives", minimum=2)
    truth = _mapping(case.get("truth"), "truth")
    _reference(truth.get("suspect"), verdict["suspects"], "truth.suspect")
    _reference(truth.get("motive"), motives, "truth.motive")
    _text(truth.get("explanation"), "truth.explanation")
    timeline = truth.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise ValueError("truth.timeline: expected chronological entries")
    for index, entry in enumerate(timeline):
        path = f"truth.timeline[{index}]"
        entry = _mapping(entry, path)
        _text(entry.get("when"), f"{path}.when")
        _text(entry.get("event"), f"{path}.event")
    _references(truth.get("clues", []), set(evidence) | set(records), "truth.clues")

    for name, role in roles.items():
        path = f"roles.{name}"
        _text(name, "roles")
        if name.startswith("$"):
            raise ValueError(f"{path}: role name uses a reserved player ID prefix")
        role = _mapping(role, path)
        for key in ("identity", "motivation", "goal"):
            _text(role.get(key), f"{path}.{key}")
        _references(role.get("interests"), topics, f"{path}.interests")
        for key in ("knowledge", "disclosure", "verify"):
            _references(role.get(key), records, f"{path}.{key}")
        for target, trust in _mapping(role.get("relations"), f"{path}.relations").items():
            _reference(target, {"$player", *roles}, f"{path}.relations")
            if type(trust) is not int:
                raise ValueError(f"{path}.relations.{target}: expected integer trust")
        _boolean(role, "availability", path)

    for key, item in evidence.items():
        path = f"evidence.{key}"
        item = _mapping(item, path)
        _text(item.get("name"), f"{path}.name")
        _text(item.get("text"), f"{path}.text")
        _reference(item.get("topic"), topics, f"{path}.topic")
        _boolean(item, "initial", path)
        if "category" in item:
            _reference(item["category"], ("physical", "document", "digital", "testimony", "combination"),
                       f"{path}.category")
        if "importance" in item:
            _reference(item["importance"], ("low", "medium", "high", "critical"), f"{path}.importance")

    for key, record in records.items():
        path = f"records.{key}"
        record = _mapping(record, path)
        _text(record.get("name"), f"{path}.name")
        _reference(record.get("kind"), ("fact", "claim"), f"{path}.kind")
        _reference(record.get("topic"), topics, f"{path}.topic")
        _boolean(record, "available", path)
        if record.get("available", True) or not isinstance(record.get("text"), str):
            _text(record.get("text"), f"{path}.text")
        if "basis" in record:
            _reference(record["basis"], ("document", "observation", "interpretation", "hearsay"), f"{path}.basis")

    for key, action in actions.items():
        path = f"actions.{key}"
        action = _mapping(action, path)
        _text(action.get("label"), f"{path}.label")
        kind = action.get("kind")
        _reference(kind, ("ask", "tell", "inspect"), f"{path}.kind")
        _references(action.get("roles"), roles, f"{path}.roles", minimum=1)
        _reference(action.get("topic"), topics, f"{path}.topic")
        _reference(action.get("target"), records if kind == "inspect" else roles, f"{path}.target")
        if kind != "inspect":
            _reference(action.get("record"), records, f"{path}.record")
        _references(action.get("requires", []), evidence, f"{path}.requires")
        _references(action.get("grants", []), evidence, f"{path}.grants")
        cost = action.get("cost", 1)
        if type(cost) is not int or cost < 1:
            raise ValueError(f"{path}.cost: expected a positive integer")

    for key, topic in topics.items():
        path = f"topics.{key}"
        topic = _mapping(topic, path)
        _text(topic.get("label"), f"{path}.label")
        _items(topic.get("aliases"), f"{path}.aliases")
        _references(topic.get("options"), actions, f"{path}.options")
        if any(actions[option]["topic"] != key for option in topic["options"]):
            raise ValueError(f"{path}.options: action belongs to a different topic")
        if "hint" in topic:
            _text(topic["hint"], f"{path}.hint")

    for topic, reactions in _mapping(case.get("reactions"), "reactions").items():
        _reference(topic, topics, "reactions")
        for role, options in _mapping(reactions, f"reactions.{topic}").items():
            path = f"reactions.{topic}.{role}"
            _reference(role, roles, path)
            _references(options, actions, path)
            if any(role not in actions[option]["roles"] for option in options):
                raise ValueError(f"{path}: reaction is not authorized for this role")

    for topic, followups in _mapping(case.get("followups"), "followups").items():
        _reference(topic, topics, "followups")
        for role, options in _mapping(followups, f"followups.{topic}").items():
            path = f"followups.{topic}.{role}"
            _reference(role, roles, path)
            options = _mapping(options, path)
            _boolean(options, "receipt", path)
            _boolean(options, "origin_requires_statement", path)

    # Detect missing or circular evidence prerequisites before a case ships.
    reachable = {key for key, item in evidence.items() if item.get("initial", True)}
    grant_actions = [action for action in actions.values() if action.get("grants")
                     and (action["kind"] != "inspect" or records[action["target"]].get("available", True))]
    while True:
        grants = {key for action in grant_actions
                  if all(key in reachable for key in action.get("requires", []))
                  for key in action.get("grants", [])} - reachable
        if not grants:
            break
        reachable.update(grants)
    if missing := set(evidence) - reachable:
        raise ValueError(f"evidence: no reachable grant for {', '.join(sorted(missing))}")
    return case
