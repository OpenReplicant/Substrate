-- Module install: environment (Substrate, S-219), the kernel's side. Applied once by `kk module install` as a superuser
-- (the kernel's modules/_template/migration.sql). The environment's own schema `env` is migrated by environment/db.py
-- (environment/sql/, numbered, each applied once); 013 there grants this role what it needs in `env`.
-- Clearance comes from the default scope grants to kk_agent (the kernel's 002_bootstrap.sql): the module submits each
-- waiting action as a change set in the review lane of urn:kk:scope:default.

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'kkm_environment') then
    create role kkm_environment nologin;
  end if;
end $$;
grant kk_agent to kkm_environment;
grant kkm_environment to kk_authenticator;       -- the module's service connects as the kernel's login and switches to it

set role kk_owner;
insert into kernel.agent(iri, db_role, kind, label)
values ('urn:kk:agent:environment', 'kkm_environment', 'software', 'Environment: actions behind gates')
on conflict (iri) do nothing;
reset role;
