-- JWT signing in SQL, for api.login. Vendored from pgjwt 0.2.0 (https://github.com/michelp/pgjwt,
-- pgjwt--0.2.0.sql; MIT, Copyright (c) 2016 Michel Pelletier; LICENSES/pgjwt-MIT.txt), as PostgREST's v16.5 docs
-- suggest for environments that do not install the extension. Only signing is kept (url_encode,
-- algorithm_sign, sign); @extschema@ is wb_crypto, where 001_core.sql installs pgcrypto.

CREATE OR REPLACE FUNCTION wb_crypto.url_encode(data bytea) RETURNS text LANGUAGE sql AS $$
    SELECT translate(encode(data, 'base64'), E'+/=\n', '-_');
$$ IMMUTABLE;

CREATE OR REPLACE FUNCTION wb_crypto.algorithm_sign(signables text, secret text, algorithm text)
RETURNS text LANGUAGE sql AS $$
WITH
  alg AS (
    SELECT CASE
      WHEN algorithm = 'HS256' THEN 'sha256'
      WHEN algorithm = 'HS384' THEN 'sha384'
      WHEN algorithm = 'HS512' THEN 'sha512'
      ELSE '' END AS id)  -- hmac throws error
SELECT wb_crypto.url_encode(wb_crypto.hmac(signables, secret, alg.id)) FROM alg;
$$ IMMUTABLE;

CREATE OR REPLACE FUNCTION wb_crypto.sign(payload json, secret text, algorithm text DEFAULT 'HS256')
RETURNS text LANGUAGE sql AS $$
WITH
  header AS (
    SELECT wb_crypto.url_encode(convert_to('{"alg":"' || algorithm || '","typ":"JWT"}', 'utf8')) AS data
    ),
  payload AS (
    SELECT wb_crypto.url_encode(convert_to(payload::text, 'utf8')) AS data
    ),
  signables AS (
    SELECT header.data || '.' || payload.data AS data FROM header, payload
    )
SELECT
    signables.data || '.' ||
    wb_crypto.algorithm_sign(signables.data, secret, algorithm) FROM signables;
$$ IMMUTABLE;
