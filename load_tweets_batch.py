#!/usr/bin/python3

# imports
import psycopg2
import sqlalchemy
import os
import datetime
import zipfile
import io
import json

################################################################################
# helper functions
################################################################################

def remove_nulls(s):
    r'''
    Postgres doesn't support strings with the null character \x00 in them, but twitter does.
    This helper function replaces the null characters with an escaped version so that they can be loaded into postgres.
    Technically, this means the data in postgres won't be an exact match of the data in twitter,
    and there is no way to get the original twitter data back from the data in postgres.

    The null character is extremely rarely used in real world text (approx. 1 in 1 billion tweets),
    and so this isn't too big of a deal.
    A more correct implementation, however, would be to *escape* the null characters rather than remove them.
    This isn't hard to do in python, but it is a bit of a pain to do with the JSON/COPY commands for the denormalized data.
    Since our goal is for the normalized/denormalized versions of the data to match exactly,
    we're not going to escape the strings for the normalized data.

    >>> remove_nulls('\x00')
    '\\x00'
    >>> remove_nulls('hello\x00 world')
    'hello\\x00 world'
    '''
    if s is None:
        return None
    else:
        return s.replace('\x00','\\x00')


        users.append({
            'id_users':tweet['user']['id'],
            'created_at':tweet['user']['created_at'],
            'updated_at':tweet['created_at'],
            'screen_name':remove_nulls(tweet['user']['screen_name']),
            'name':remove_nulls(tweet['user']['name']),
            'location':remove_nulls(tweet['user']['location']),
            'url':remove_null(tweet['id']['url']),
            'description':remove_nulls(tweet['user']['description']),
            'protected':tweet['user']['protected'],
            'verified':tweet['user']['verified'],
            'friends_count':tweet['user']['friends_count'],
            'listed_count':tweet['user']['listed_count'],
            'favourites_count':tweet['user']['favourites_count'],
            'statuses_count':tweet['user']['statuses_count'],
            'withheld_in_countries':tweet['user'].get('withheld_in_countries',None),
            })

        ########################################
        # insert into the tweets table
        ########################################

        try:
            geo_coords = tweet['geo']['coordinates']
            geo_coords = str(tweet['geo']['coordinates'][0]) + ' ' + str(tweet['geo']['coordinates'][1])
            geo_str = 'POINT'
        except TypeError:
            try:
                geo_coords = '('
                for i,poly in enumerate(tweet['place']['bounding_box']['coordinates']):
                    if i>0:
                        geo_coords+=','
                    geo_coords+='('
                    for j,point in enumerate(poly):
                        geo_coords+= str(point[0]) + ' ' + str(point[1]) + ','
                    geo_coords+= str(poly[0][0]) + ' ' + str(poly[0][1])
                    geo_coords+=')'
                geo_coords+=')'
                geo_str = 'MULTIPOLYGON'
            except KeyError:
                if tweet['user']['geo_enabled']:
                    geo_str = None
                    geo_coords = None

        try:
            text = tweet['extended_tweet']['full_text']
        except:
            text = tweet['text']

        try:
            country_code = tweet['place']['country_code'].lower()
        except TypeError:
            country_code = None

        if country_code == 'us':
            state_code = tweet['place']['full_name'].split(',')[-1].strip().lower()
            if len(state_code)>2:
                state_code = None
        else:
            state_code = None

        try:
            place_name = tweet['place']['full_name']
        except TypeError:
            place_name = None

        # NOTE:
        # The tweets table has the following foreign key:
        # > FOREIGN KEY (in_reply_to_user_id) REFERENCES users(id_users)
        #
        # This means that every "in_reply_to_user_id" field must reference a valid entry in the users table.
        # If the id is not in the users table, then you'll need to add it in an "unhydrated" form.
        if tweet.get('in_reply_to_user_id',None) is not None:
            users_unhydrated_from_tweets.append({
                'id_users':tweet['in_reply_to_user_id'],
                'screen_name':tweet['in_reply_to_screen_name'],
                })

        # insert the tweet
        tweets.append({
            'id_tweets':tweet['id'],
            'id_users':tweet['user']['id'],
            'created_at':tweet['created_at'],
            'in_reply_to_status_id':tweet.get('in_reply_to_status_id',None),
            'in_reply_to_user_id':tweet.get('in_reply_to_user_id',None),
            'quoted_status_id':tweet.get('quoted_status_id',None),
            'geo_coords':geo_coords,
            'geo_str':geo_str,
            'retweet_count':tweet.get('retweet_count',None),
            'quote_count':tweet.get('quote_count',None),
            'favorite_count':tweet.get('favorite_count',None),
            'withheld_copyright':tweet.get('withheld_copyright',None),
            'withheld_in_countries':tweet.get('withheld_in_countries',None),
            'place_name':place_name,
            'country_code':country_code,
            'state_code':state_code,
            'lang':tweet.get('lang'),
            'text':remove_nulls(text),
            'source':remove_nulls(tweet.get('source',None)),
            })


        ########################################
        # insert into the tweet_mentions table
        ########################################

        try:
            mentions = tweet['extended_tweet']['entities']['user_mentions']
        except KeyError:
            mentions = tweet['entities']['user_mentions']

        for mention in mentions:
            users_unhydrated_from_mentions.append({
                'id_users':mention['id'],
                'name':remove_nulls(mention['name']),
                'screen_name':remove_nulls(mention['screen_name']),
                })

            tweet_mentions.append({
                'id_tweets':tweet['id'],
                'id_users':mention['id']
                })

        ########################################
        # insert into the tweet_tags table
        ########################################

        try:
            hashtags = tweet['extended_tweet']['entities']['hashtags'] 
            cashtags = tweet['extended_tweet']['entities']['symbols'] 
        except KeyError:
            hashtags = tweet['entities']['hashtags']
            cashtags = tweet['entities']['symbols']

        tags = [ '#'+hashtag['text'] for hashtag in hashtags ] + [ '$'+cashtag['text'] for cashtag in cashtags ]

        for tag in tags:
            tweet_tags.append({
                'id_tweets':tweet['id'],
                'tag':remove_nulls(tag)
                })

        ########################################
        # insert into the tweet_media table
        ########################################

        try:
            media = tweet['extended_tweet']['extended_entities']['media']
        except KeyError:
            try:
                media = tweet['extended_entities']['media']
            except KeyError:
                media = []

        for medium in media:
            tweet_media.append({
                'id_tweets':tweet['id'],
                'url':tweet['url'],
                'type':medium['type']
                })

    ######################################## 
    # STEP 2: perform the actual SQL inserts
    ######################################## 
    with connection.begin() as trans:

        # use the bulk_insert function to insert most of the data
        bulk_insert(connection, 'users', users)
        bulk_insert(connection, 'users', users_unhydrated_from_tweets)
        bulk_insert(connection, 'users', users_unhydrated_from_mentions)
        bulk_insert(connection, 'tweet_mentions', tweet_mentions)
        bulk_insert(connection, 'tweet_tags', tweet_tags)
        bulk_insert(connection, 'tweet_media', tweet_media)

        # the tweets data cannot be inserted using the bulk_insert function because
        # the geo column requires special SQL code to generate the column;
        #
        # NOTE:
        # in general, it is a good idea to avoid designing tables that require special SQL on the insertion;
        # it makes your python code much more complicated,
        # and is also bad for performance;
        # I'm doing it here just to help illustrate the problems
        sql = sqlalchemy.sql.text('''
        INSERT INTO tweets
            (id_tweets,id_users,created_at,in_reply_to_status_id,in_reply_to_user_id,quoted_status_id,geo,retweet_count,quote_count,favorite_count,withheld_copyright,withheld_in_countries,place_name,country_code,state_code,lang,text,source)
            VALUES
            '''
            +
            ','.join([f"(:id_tweets{i},:id_users{i},:created_at{i},:in_reply_to_status_id{i},:in_reply_to_user_id{i},:quoted_status_id{i},ST_GeomFromText(:geo_str{i} || '(' || :geo_coords{i} || ')'), :retweet_count{i},:quote_count{i},:favorite_count{i},:withheld_copyright{i},:withheld_in_countries{i},:place_name{i},:country_code{i},:state_code{i},:lang{i},:text{i},:source{i})" for i in range(len(tweets))])
            +
            '''
            ON CONFLICT DO NOTHING
            '''
            )
        res = connection.execute(sql, { key+str(i):value for i,tweet in enumerate(tweets) for key,value in tweet.items() })


if __name__ == '__main__':

    # process command line args
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--inputs',nargs='+',required=True)
    parser.add_argument('--batch_size',type=int,default=1000)
    args = parser.parse_args()

    # create database connection
    engine = sqlalchemy.create_engine(args.db, connect_args={
        'application_name': 'load_tweets.py --inputs '+' '.join(args.inputs),
        })
    connection = engine.connect()

    # loop through file
    # NOTE:
    # we reverse sort the filenames because this results in fewer updates to the users table,
    # which prevents excessive dead tuples and autovacuums
    with connection.begin() as trans:
        for filename in sorted(args.inputs, reverse=True):
            with zipfile.ZipFile(filename, 'r') as archive: 
                print(datetime.datetime.now(),filename)
                for subfilename in sorted(archive.namelist(), reverse=True):
                    with io.TextIOWrapper(archive.open(subfilename)) as f:
                        tweets = []
                        for i,line in enumerate(f):
                            tweet = json.loads(line)
                            tweets.append(tweet)
                        insert_tweets(connection,tweets,args.batch_size)
