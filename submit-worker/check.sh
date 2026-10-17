#!/bin/bash
# The checks that are only convincing against something running.
#
#   npx wrangler dev --local --port 8787     # in one terminal
#   ./check.sh                               # in another
#
# Every case here is a defect that was live, or that review found in the plan before it was
# written. None of them is visible from the happy path, which is the whole reason this file
# exists. Run it before a deploy. It writes to the *local* database only.
#
# WHAT THIS CANNOT COVER, stated rather than implied: a *successful* sign-in, and the
# signature check itself. Nothing here can mint a token Google has signed, so that much is a
# device test and only a device test. Everything the signature check guards — the audience,
# the expiry, email_verified — is covered by test/claims.test.js instead, which runs first. There is deliberately no DEV-mode bypass that would accept an unsigned token — the
# previous version of this Worker printed sign-in codes to the production log because a dev
# convenience had a weak check on where it was running, and that is the standing reminder.

set -u
B="${1:-http://127.0.0.1:8787}"
pass=0
fail=0

# The claim checks first, directly, with no server and no network.
#
# They have to be tested this way. Every token these HTTP cases can build is refused by the
# signature check long before a claim is compared, so deleting the audience comparison
# outright still left this file reporting all green. node --test reaches them.
echo "Claim checks (node --test)"
if node --test test/claims.test.js > /dev/null 2>&1; then
  printf '  ok    claims\n'; pass=$((pass + 1))
else
  printf '  FAIL  claims — run: node --test test/claims.test.js\n'; fail=$((fail + 1))
fi
echo

check() { # check <name> <expected status> <actual status>
  if [ "$2" = "$3" ]; then
    printf '  ok    %s\n' "$1"; pass=$((pass + 1))
  else
    printf '  FAIL  %s — wanted %s, got %s\n' "$1" "$2" "$3"; fail=$((fail + 1))
  fi
}

post() { # post <path> <json> -> prints the status
  curl -s -o /dev/null -w '%{http_code}' -X POST "$B$1" -H 'content-type: application/json' --data-binary "$2"
}

token() { # token <raw json value for idToken> -> a JSON body
  printf '{"idToken":%s}' "$1"
}

# A well-formed JWT: real base64url, real JSON, and a signature that is simply wrong. Google
# never signed it, so every one of these must be refused at the signature or before it.
seg() { printf '%s' "$1" | base64 | tr '+/' '-_' | tr -d '='; }
HEAD=$(seg '{"alg":"RS256","kid":"nope","typ":"JWT"}')
HEAD_NONE=$(seg '{"alg":"none","kid":"nope","typ":"JWT"}')
NOW=$(date +%s)
BODY=$(seg "{\"iss\":\"https://accounts.google.com\",\"aud\":\"1072147454316-1vfqpurdr084eabr3q87pojqv370bf3o.apps.googleusercontent.com\",\"sub\":\"1\",\"email\":\"a@b.com\",\"email_verified\":true,\"exp\":$((NOW + 3600)),\"iat\":$NOW}")
BODY_NOAUD=$(seg "{\"iss\":\"https://accounts.google.com\",\"sub\":\"1\",\"email\":\"a@b.com\",\"email_verified\":true,\"exp\":$((NOW + 3600)),\"iat\":$NOW}")
BODY_UNVERIFIED=$(seg "{\"iss\":\"https://accounts.google.com\",\"aud\":\"1072147454316-1vfqpurdr084eabr3q87pojqv370bf3o.apps.googleusercontent.com\",\"sub\":\"1\",\"email\":\"a@b.com\",\"email_verified\":\"false\",\"exp\":$((NOW + 3600)),\"iat\":$NOW}")
SIG="bm90YXNpZ25hdHVyZQ"

# All of these answer 401, not 400, and deliberately: an honest client always sends a
# well-formed token, so distinguishing "shaped wrong" from "not signed" helps only somebody
# probing. One refusal, one wording.
echo "Shapes that are not a token at all"
check "idToken []"                 401 "$(post /account/google "$(token '[]')")"
check "idToken {}"                 401 "$(post /account/google "$(token '{}')")"
check "idToken \"\""                 401 "$(post /account/google "$(token '""')")"
check "two parts"                  401 "$(post /account/google "$(token '"a.b"')")"
check "three empty parts"          401 "$(post /account/google "$(token '"..",""')" 2>/dev/null)"
check "not base64url"              401 "$(post /account/google "$(token '"!!!.!!!.!!!"')")"
check "no body at all"             401 "$(post /account/google '{}')"

echo "Tokens Google did not sign"
check "unsigned, otherwise valid"  401 "$(post /account/google "$(token "\"$HEAD.$BODY.$SIG\"")")"
check "alg none"                   401 "$(post /account/google "$(token "\"$HEAD_NONE.$BODY.$SIG\"")")"
# The regression test for the hole that matters most: an unset audience variable would make
# the comparison undefined !== undefined, which is false, which accepts this.
check "no aud claim"               401 "$(post /account/google "$(token "\"$HEAD.$BODY_NOAUD.$SIG\"")")"
# email_verified as the *string* "false" is truthy. `if (claim)` would accept it.
check "email_verified \"false\""     401 "$(post /account/google "$(token "\"$HEAD.$BODY_UNVERIFIED.$SIG\"")")"

echo "Nothing is accepted without a Peel token"
check "upload without one"         401 "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$B/packs" -F pack=@/dev/null)"
check "delete without one"         401 "$(post /account/delete '{}')"
check "delete with a made-up one"  401 "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$B/account/delete" -H 'authorization: Bearer nope' -H 'content-type: application/json' --data-binary '{}')"

echo "The old surface is gone, not merely unused"
for path in /account/code /account/verify /account/signin /account/password; do
  check "$path"                    404 "$(post "$path" '{"email":"a@b.com","name":"A"}')"
done

echo "Only POST"
check "GET /account/google"        405 "$(curl -s -o /dev/null -w '%{http_code}' "$B/account/google")"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
