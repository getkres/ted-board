import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_data_api_grants.py"


class DataApiGrantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("grants", SCRIPT)
        cls.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.guard)

    def errors(self, sql):
        return self.guard.check_sql(sql)

    def test_missing_grant_fails(self):
        self.assertTrue(self.errors("create table public.example(id int); alter table public.example enable row level security;"))

    def test_service_role_crud_and_rls_pass(self):
        self.assertEqual(self.errors('''create table "public"."Example"(id int);
grant select, insert, update, delete on table "public"."Example" to service_role;
alter table "public"."Example" enable row level security;'''), [])

    def test_partial_grants_wrong_table_and_missing_rls_fail(self):
        for suffix in ["grant select on example to service_role;", "grant all on other to service_role;", "grant all on example to authenticated;"]:
            self.assertTrue(self.errors("create table example(id int); alter table example enable row level security;" + suffix))
        self.assertTrue(self.errors("create table example(id int); grant all on example to service_role;"))

    def test_comments_strings_and_function_bodies_cannot_supply_grants(self):
        for fake in ["-- grant all on example to service_role;", "/* grant all on example to service_role; */", "select 'grant all on example to service_role;';", "do $x$ begin grant all on example to service_role; end $x$;"]:
            self.assertTrue(self.errors("create table example(id int); alter table example enable row level security;" + fake))
        self.assertEqual(self.errors("select 'create table fake(id int);'; -- create table nope(id int);"), [])

    def test_multi_table_grants_split_privileges_and_revokes(self):
        sql = '''create table a(id int); create table b(id int);
grant select, insert on a, b to service_role;
grant update, delete on table a, b to service_role;
alter table a enable row level security; alter table b enable row level security;'''
        self.assertEqual(self.errors(sql), [])
        self.assertTrue(self.errors(sql + "revoke delete on b from service_role;"))
        self.assertTrue(self.errors(sql + "alter table b disable row level security;"))

    def test_temp_private_and_quoted_nonpublic_are_ignored(self):
        self.assertEqual(self.errors('create temporary table example(id int); create table private.example(id int); create table "PUBLIC".example(id int);'), [])

    def test_cutoffs_cover_all_roots_and_exclude_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory, cutoff in self.guard.CUTOFFS.items():
                migrations = root / directory
                migrations.mkdir(parents=True)
                (migrations / (cutoff + "_old.sql")).write_text("create table old(id int);")
                self.assertEqual(self.guard.check_repository(root)[0], [])
                newer = str(int(cutoff) + 1)
                path = migrations / (newer + "_new.sql")
                path.write_text("create table fresh(id int);")
                self.assertTrue(self.guard.check_repository(root)[0])
                path.unlink()

    def test_each_created_table_needs_its_own_grant(self):
        sql = '''create table a(id int); create table b(id int);
grant all on a to service_role;
alter table a enable row level security; alter table b enable row level security;'''
        self.assertTrue(any("public.b" in error for error in self.errors(sql)))

    def test_grant_before_create_and_column_grant_do_not_count(self):
        self.assertTrue(self.errors("grant all on a to service_role; create table a(id int); alter table a enable row level security;"))
        self.assertTrue(self.errors("create table a(id int); grant select(id), insert, update, delete on a to service_role; alter table a enable row level security;"))

    def test_revoke_modifiers_still_remove_access(self):
        sql = "create table a(id int); grant all on a to service_role; alter table a enable row level security;"
        for modifier in ["cascade", "restrict"]:
            self.assertTrue(self.errors(sql + "revoke all on a from service_role " + modifier + ";"))

    def test_escape_strings_cannot_supply_grants(self):
        sql = r"create table a(id int); alter table a enable row level security; select E'\'; grant all on a to service_role;';"
        self.assertTrue(self.errors(sql))

    def test_procedural_dynamic_creation_is_rejected(self):
        self.assertTrue(self.errors("do $$ begin execute 'create ' || 'table public.a(id int)'; end $$;"))
        self.assertTrue(self.errors("do $$ begin create table a(id int); end $$;"))

    def test_dollar_data_and_body_comments_are_ignored(self):
        self.assertEqual(self.errors("select $$create table a(id int);$$;"), [])
        self.assertEqual(self.errors("do $$ begin /* create table a(id int); */ perform 1; end $$;"), [])

    def test_quoted_comma_and_grant_option(self):
        self.assertEqual(self.errors('create table "a,b"(id int); grant all on "a,b" to service_role with grant option; alter table "a,b" enable row level security;'), [])

    def test_renames_and_schema_moves_cannot_hide_missing_access(self):
        sql = "create table a(id int); grant all on a to service_role; alter table a enable row level security; alter table a rename to b;"
        self.assertEqual(self.errors(sql), [])
        self.assertTrue(self.errors(sql + "revoke all on b from service_role;"))
        self.assertTrue(self.errors("create table private.a(id int); alter table private.a set schema public;"))

    def test_multi_action_alter_uses_final_rls_state(self):
        sql = "create table a(id int); grant all on a to service_role; alter table a enable row level security;"
        self.assertTrue(self.errors(sql + "alter table a enable row level security, disable row level security;"))
        self.assertEqual(self.errors(sql + "alter table a disable row level security, enable row level security;"), [])

    def test_procedural_revokes_and_search_path_cannot_hide_access(self):
        sql = "create table a(id int); grant all on a to service_role; alter table a enable row level security;"
        self.assertTrue(self.errors(sql + "do $$ begin revoke all on a from service_role; end $$;"))
        self.assertTrue(self.errors(sql + "do $$ begin alter table a disable row level security; end $$;"))
        self.assertTrue(self.errors("set local search_path = private, public;" + sql))
        self.assertTrue(self.errors("select set_config('search_path', 'private', true);" + sql))


if __name__ == "__main__":
    unittest.main()
