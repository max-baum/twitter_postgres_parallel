#!/bin/bash

files=$(find data/*)

echo '================================================================================'
echo 'load denormalized'
echo '================================================================================'
time for file in $files; do
    echo
    unzip -p "$file" > temp_raw.txt

    cat temp_raw.txt | sed 's/\\u0000//g' | psql postgresql://postgres:pass@localhost:6767/postgres -c "COPY tweets_jsonb (data) FROM STDIN csv quote e'\x01' delimiter e'\x02';"
    # copy your solution to the twitter_postgres assignment here
done

echo '================================================================================'
echo 'load pg_normalized'
echo '================================================================================'
time for file in $files; do
    echo
    # copy your solution to the twitter_postgres assignment here
    python3 load_tweets.py --db=postgresql://postgres:pass@localhost:6768/postgres --inputs="$f    ile"
done

echo '================================================================================'
echo 'load pg_normalized_batch'
echo '================================================================================'
time for file in $files; do
    python3 -u load_tweets_batch.py --db=postgresql://postgres:pass@localhost:3/ --inputs $file
done
