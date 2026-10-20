#!/usr/bin/env python3
"""Offline guard for future public tables. Uses only the Python standard library."""

import argparse
from pathlib import Path
import re

# Fixed adoption boundaries, never derive these from the current directory contents.
CUTOFFS = {
    "supabase/migrations": "20261017030000",
    "mockups-backend/supabase/migrations": "20261016160000",
    "mockups-verification/supabase/migrations": "20261016160000",
}
CRUD = {"select", "insert", "update", "delete"}
IDENTIFIER = r'(?:"(?:[^"]|"")+"|[a-zA-Z_][a-zA-Z_0-9$]*)'
RELATION = rf'{IDENTIFIER}(?:\s*\.\s*{IDENTIFIER})?'
TOKEN = re.compile(
    r"--[^\n]*|/\*|\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$|[eE]'(?:\\.|''|[^'\\])*'|'(?:''|[^'])*'|"
    + IDENTIFIER + r"|[^\s]",
    re.DOTALL,
)
PROCEDURAL_MUTATION = re.compile(
    r"\bcreate\s+(?:unlogged\s+)?table\b|\b(?:execute|grant|revoke|set_config)\b|\brow\s+level\s+security\b|\bsearch_path\b",
    re.I,
)


def statements(sql):
    """Tokenize SQL, ignoring nested comments and non-executable literal contents."""
    result, current, unsupported = [], [], []
    cursor = 0
    while cursor < len(sql):
        match = TOKEN.search(sql, cursor)
        if not match:
            break
        token = match.group()
        cursor = match.end()
        if token.startswith("--"):
            continue
        if token == "/*":
            depth = 1
            while depth and cursor < len(sql):
                boundary = re.search(r"/\*|\*/", sql[cursor:])
                if not boundary:
                    cursor = len(sql)
                    break
                depth += 1 if boundary.group() == "/*" else -1
                cursor += boundary.end()
            continue
        procedural = re.match(r"^(?:do\b|create\s+(?:or\s+replace\s+)?(?:function|procedure)\b)", " ".join(current), re.I)
        if token.startswith("$"):
            end = sql.find(token, cursor)
            body = sql[cursor:end] if end >= 0 else sql[cursor:]
            if procedural:
                nested, nested_errors = statements(body)
                unsupported.extend(nested_errors)
                executable = " ".join(nested)
                # Conservatively reject dynamic SQL, which can assemble arbitrary DDL.
                if PROCEDURAL_MUTATION.search(executable):
                    unsupported.append("Procedural DDL, ACL, RLS, search_path, or dynamic EXECUTE requires review and literal top-level migration SQL.")
            cursor = end + len(token) if end >= 0 else len(sql)
            current.append("<literal>")
        elif token.startswith(("'", "E'", "e'")):
            if procedural:
                body = token[2:-1] if token.startswith(("E'", "e'")) else token[1:-1]
                nested, nested_errors = statements(body.replace("''", "'"))
                unsupported.extend(nested_errors)
                if PROCEDURAL_MUTATION.search(" ".join(nested)):
                    unsupported.append("Procedural DDL, ACL, RLS, search_path, or dynamic EXECUTE requires review and literal top-level migration SQL.")
            if current and current[-1].lower() == "execute" and re.search(r"\bcreate\s+table\b", token, re.I):
                unsupported.append("Dynamic table DDL requires a literal top-level migration and explicit grants.")
            current.append("<literal>")
        elif token == ";":
            result.append(" ".join(current))
            current = []
        else:
            current.append(token)
    if current:
        result.append(" ".join(current))
    return result, unsupported


def name(value):
    parts = re.findall(IDENTIFIER, value)
    parts = [part[1:-1].replace('""', '"') if part.startswith('"') else part.lower() for part in parts]
    if len(parts) == 1:
        return "public", parts[0]
    return tuple(parts)


def comma_list(value):
    return [part.strip() for part in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', value)]


def check_sql(sql):
    """Require explicit service-role CRUD and enabled RLS in each creating file."""
    sql_statements, errors = statements(sql)
    created = {}
    for statement in sql_statements:
        if re.match(r"^set\s+(?:(?:local|session)\s+)?search_path\b", statement, re.I) or re.search(r"\bset_config\s*\(", statement, re.I):
            errors.append("SET search_path or set_config requires review; use schema-qualified names and literal top-level access controls.")
        create = re.match(rf"^create\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?({RELATION})", statement, re.I)
        if create:
            table = name(create[1])
            created[table] = {"grants": set(), "rls": False}
            continue
        access = re.fullmatch(r"(grant|revoke)\s+(.+?)\s+on\s+(?:table\s+)?(.+?)\s+(?:to|from)\s+(.+)", statement, re.I)
        if access:
            # Never accept grants on a function, sequence, or every table in a schema.
            tables = comma_list(access[3])
            if not all(re.fullmatch(RELATION, table) for table in tables):
                continue
            role_text = re.sub(r"\s+(?:cascade|restrict|with\s+grant\s+option)$", "", access[4], flags=re.I)
            roles = {name(role)[-1] for role in comma_list(role_text) if re.fullmatch(IDENTIFIER, role)}
            if "service_role" not in roles:
                continue
            privileges = {p.strip().lower() for p in access[2].split(",")}
            if privileges & {"all", "all privileges"}:
                privileges = CRUD
            for table in tables:
                entry = created.get(name(table))
                if entry is not None:
                    if access[1].lower() == "grant":
                        entry["grants"].update(privileges & CRUD)
                    else:
                        entry["grants"].difference_update(privileges & CRUD)
            continue
        alter = re.fullmatch(rf"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?({RELATION})\s+(.+)", statement, re.I)
        if alter and name(alter[1]) in created:
            for action in comma_list(alter[2]):
                rls = re.fullmatch(r"(enable|disable)\s+row\s+level\s+security", action, re.I)
                if rls:
                    created[name(alter[1])]["rls"] = rls[1].lower() == "enable"
        rename = re.fullmatch(rf"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?({RELATION})\s+(rename\s+to|set\s+schema)\s+({IDENTIFIER})", statement, re.I)
        if rename and name(rename[1]) in created:
            previous = name(rename[1])
            target = name(rename[3])[-1]
            next_name = (previous[0], target) if rename[2].lower().startswith("rename") else (target, previous[1])
            created[next_name] = created.pop(previous)
    for table, entry in created.items():
        if table[0] != "public":
            continue
        label = ".".join(table)
        missing = CRUD - entry["grants"]
        if missing:
            errors.append(f"{label}: missing explicit service_role grants: {', '.join(sorted(missing))}")
        if not entry["rls"]:
            errors.append(f"{label}: missing ENABLE ROW LEVEL SECURITY")
    return errors


def check_repository(root):
    errors, checked = [], 0
    for directory, cutoff in CUTOFFS.items():
        for path in sorted((Path(root) / directory).glob("*.sql")):
            version = path.name.split("_", 1)[0]
            if not version.isdigit():
                errors.append(f"{path.relative_to(root)}: migration filename must start with a numeric version")
                continue
            if int(version) <= int(cutoff):
                continue
            checked += 1
            errors.extend(f"{path.relative_to(root)}: {message}" for message in check_sql(path.read_text()))
    return errors, checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Repository or local operational checkout to inspect")
    args = parser.parse_args()
    errors, checked = check_repository(args.root.resolve())
    for error in errors:
        print(error)
    print(f"Checked {checked} future migration(s) across {len(CUTOFFS)} roots.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
