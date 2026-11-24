package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"regexp"
	"strings"
	"time"
)

// The Knowledge Kernel's token format (repos/kernel/kk/cli.py mint): an HS256 JWT with claims role, iat, exp.

type claims struct {
	Role string `json:"role"`
	Iat  int64  `json:"iat"`
	Exp  int64  `json:"exp"`
}

var b64 = base64.RawURLEncoding

func mintToken(role, secret string, ttl time.Duration, now time.Time) string {
	head := b64.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	body, _ := json.Marshal(claims{Role: role, Iat: now.Unix(), Exp: now.Add(ttl).Unix()})
	msg := head + "." + b64.EncodeToString(body)
	return msg + "." + b64.EncodeToString(sign(msg, secret))
}

func sign(msg, secret string) []byte {
	m := hmac.New(sha256.New, []byte(secret))
	m.Write([]byte(msg))
	return m.Sum(nil)
}

var errToken = errors.New("invalid token")

// verifyToken returns the token's role. It accepts only HS256, checks the signature in constant time and exp
// (a token without exp is refused), and requires a role.
func verifyToken(token, secret string, now time.Time) (string, error) {
	if secret == "" {
		return "", errToken
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return "", errToken
	}
	hb, err := b64.DecodeString(parts[0])
	if err != nil {
		return "", errToken
	}
	var h struct {
		Alg string `json:"alg"`
	}
	if json.Unmarshal(hb, &h) != nil || h.Alg != "HS256" {
		return "", errToken
	}
	sig, err := b64.DecodeString(parts[2])
	if err != nil || !hmac.Equal(sig, sign(parts[0]+"."+parts[1], secret)) {
		return "", errToken
	}
	bb, err := b64.DecodeString(parts[1])
	if err != nil {
		return "", errToken
	}
	var c claims
	if json.Unmarshal(bb, &c) != nil || c.Role == "" || c.Exp == 0 || now.Unix() >= c.Exp {
		return "", errToken
	}
	return c.Role, nil
}

var personName = regexp.MustCompile(`^[a-z0-9_-]{1,40}$`)

// personRole maps a sign-in name to its Postgres role: person_<name>, with - as _.
func personRole(name string) (string, bool) {
	if !personName.MatchString(name) {
		return "", false
	}
	return "person_" + strings.ReplaceAll(name, "-", "_"), true
}

func isPerson(role string) bool {
	return strings.HasPrefix(role, "person_") && len(role) > len("person_")
}

func bearer(h string) string {
	if len(h) > 7 && strings.EqualFold(h[:7], "bearer ") {
		return strings.TrimSpace(h[7:])
	}
	return ""
}
