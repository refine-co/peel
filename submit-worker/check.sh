#!/bin/bash
# The checks that are only convincing against something running.
#
#   npx wrangler dev --local --port 8787 --var DEV:1     # in one terminal
#   ./check.sh                                           # in another
#
# Every case here is a defect that was live on the deployed Worker on 17 Oct 2026 and is
# invisible from the happy path, which is why a passing device test did not catch any of them.
# Run it before a deploy. It writes to the *local* database only.

set -u
B="${1:-http://127.0.0.1:8787}"
pass=0
fail=0

check() { # check <name> <expected status> <actual status>
  if [ "$2" = "$3" ]; then
    printf '  ok    %s\n' "$1"; pass=$((pass + 1))
  else
    printf '  FAIL  %s — wanted %s, got %s\n' "$1" "$2" "$3"; fail=$((fail + 1))
  fi
}

post() { # post <path> <json>  -> prints the status
  curl -s -o /dev/null -w '%{http_code}' -X POST "$B$1" -H 'content-type: application/json' --data-binary "$2"
}

body() { # body <email> <field> <raw json value>  -> a JSON object
  printf '{"email":"%s","%s":%s}' "$1" "$2" "$3"
}

stamp=$(date +%s)
victim="victim-$stamp@example.com"
rate="rate-$stamp@example.com"
brute="brute-$stamp@example.com"

echo "Account takeover (a wrong password used to leave an empty code behind, which verify matched)"
check "a code can be asked for"        204 "$(post /account/code "$(body "$victim" name '"V"')")"
check "a wrong password is refused"    401 "$(post /account/signin "$(body "$victim" password '"wrong-one"')")"
check "verify refuses code []"         400 "$(post /account/verify "$(body "$victim" code '[]')")"
check "verify refuses an empty code"   400 "$(post /account/verify "$(body "$victim" code '""')")"
check "verify refuses code {}"         400 "$(post /account/verify "$(body "$victim" code '{}')")"
check "verify refuses a short code"    400 "$(post /account/verify "$(body "$victim" code '"123"')")"
check "verify refuses a wrong code"    401 "$(post /account/verify "$(body "$victim" code '"000000"')")"
check "a name that is not a string"    400 "$(post /account/code "$(body "$victim" name '[]')")"

echo "Codes per address per hour (the old query counted a primary key, so it was always 0 or 1)"
ask_rate=$(body "$rate" name '"R"')
for i in 1 2 3 4 5; do post /account/code "$ask_rate" > /dev/null; done
check "the sixth is refused"           429 "$(post /account/code "$ask_rate")"

echo "Guesses per code (asking for another used to reset the counter, so there was no ceiling)"
guess=$(body "$brute" code '"000000"')
post /account/code "$(body "$brute" name '"B"')" > /dev/null
for i in 1 2 3 4 5; do post /account/verify "$guess" > /dev/null; done
check "the sixth guess is refused"     429 "$(post /account/verify "$guess")"

echo "Nothing is accepted without a token"
check "upload without one"             401 "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$B/packs" -F pack=@/dev/null)"
check "password without one"           401 "$(post /account/password '{"password":"longenough"}')"
check "delete without one"             401 "$(post /account/delete '{}')"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
