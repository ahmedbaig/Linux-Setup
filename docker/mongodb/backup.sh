#!/bin/bash

host=localhost
port=27017
out_dir=/home/admin/dump
repo_dir=/home/admin/mongodb/database-backup

if [ ! $out_dir ]; then
        out_dir="/home/admin/dump"
else
	echo "Removing old database directory .. " >> /home/admin/dump.log
	rm -rf "$out_dir.tar.gz"
        mkdir -p $out_dir
fi

if [ ! $host ]; then
        host=localhost
fi

if [ ! $port ]; then
        port=27017
fi

declare -a db=("DAU")

for db in "${db[@]}"
do
        echo "$db"
        mkdir -p $out_dir/$db
        # read all the collections in the database specified, loop through each collection and export to json files.
        collections="$(mongosh --host $host --port $port $db --eval 'db.getCollectionNames()' --quiet  | awk 'NF > 0' | sed 's/\"//g' | sed 's/\,//g' | sed 's/\]//g' | sed 's/\[//g' | cut -f2)"
        for collection in $collections
        do
                collection_trim=`echo $collection | sed -e "s/'//g"`
                echo "`date` | ################ Exporting from $db collection $collection from $host ################" >> /home/dmgdev/dump.log
                mongoexport --host $host --port $port -d $db -c $collection_trim -o $out_dir/$db/${collection_trim}.json
        done
done

echo "Commiting changes to git ... " >> /home/dmgdev/dump.log

cp -r $out_dir $repo_dir
cp /home/dmgdev/dump.log $repo_dir/updates.log
cd $repo_dir && git add . && git commit -m "`date`" && git push origin master

echo "`date` | Backed up all databases .. zipping them up now" >> /home/dmgdev/dump.log
tar czf "$out_dir.tar.gz" $out_dir
echo "`date` | Done with zip .. deleteing the dump folder now" >> /home/dmgdev/dump.log
rm -rf $out_dir
