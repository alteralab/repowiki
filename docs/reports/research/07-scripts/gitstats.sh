#!/bin/bash
# usage: gitstats.sh <repo-dir> <jira-regex>
r=$1; J=$2; cd $r
echo "## $r"
echo "commits: $(git rev-list --count HEAD)"
echo "first: $(git log --reverse --format=%ad --date=short | head -1)  last: $(git log -1 --format=%ad --date=short)"
echo "tags: $(git tag | wc -l)  latest by date:"; git for-each-ref --sort=-creatordate --format='%(refname:short) %(creatordate:short)' refs/tags | head -5
echo "-- top 10 committers (author)"; git shortlog -sn --no-merges HEAD | head -10
echo "-- unique authors: $(git shortlog -sn HEAD | wc -l)"
echo "-- commits per year"; git log --format=%ad --date=format:%Y | sort | uniq -c | tail -20 | tr '\n' ';'; echo
echo "-- subject patterns (share of commits)"
total=$(git rev-list --count HEAD)
git log --format=%s > /tmp/subjects.$$ 
for p in "$J" '^MINOR' 'KIP-[0-9]+' 'Merge pull request' '\(#[0-9]+\)' '#[0-9]+' 'Revert' ; do c=$(grep -Ec "$p" /tmp/subjects.$$); echo "  $p : $c ($(python3 -c "print(round(100*$c/$total,1))")%)"; done
echo "-- merge commits: $(git rev-list --merges --count HEAD)"
rm /tmp/subjects.$$
