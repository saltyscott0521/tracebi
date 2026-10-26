# Connect a database

Add a database, or a file, as a source from the app, and choose which of its
tables an agent may read. The app writes `connections/<name>.yaml` as you
would by hand, and keeps any secret in the project's encrypted store.

## Before you begin

- A server with sign-in turned on ([[sign-in]]) and the `admin` role. Without
  sign-in, the app shows connections but does not change them: run
  `tracebi connect` on the server instead (see the last section).
- The database's address and a user that can read it. A read-only user is
  enough: TraceBi never writes to a source.

## Add the connection

The sheet has three steps.

**1. Choose a database.** Open **Data › Sources** and click **Add a
connection**. Pick the type from its group: **Databases** (Postgres, MySQL,
SQLite or another SQL database, DuckDB), **Warehouses** (Snowflake,
BigQuery) or **Files** (a folder of CSV files, an uploaded CSV or Parquet
file).

**2. Connect.**

1. **Name** is how a transform reads it: `-- source: <name>.<table>`.
   **Label** is the name people see, and is optional.
2. For Postgres, MySQL and Snowflake, say the connection on the **Fields**
   tab (host, port, database, user) or the **URL** tab. They are two views of
   one connection: typing in either fills the other. A URL you paste with a
   password in it moves the password to the password field.
3. The password is hidden; **Show** reveals it. **Save password** is on by
   default: the password goes to the project's encrypted store and the file
   says `password: ${TRACEBI_<NAME>_PASSWORD}`. Turn it off to keep the
   password out of the app: type the **Variable name** the server sets in its
   environment or `.env`. Until it is set there, the connection's
   credentials read **Missing**.
4. **Advanced** holds SSL, extra options and the connect timeout.
5. Click **Test**. The app opens the connection, counts its tables, reads the
   server's version and closes it. Nothing is saved yet. With Save password
   off and the variable set nowhere, Test says exactly that.
6. Click **Save**.

**3. Tables.** The connection's panel opens on its tables, ready for the next
section.

## Choose what agents may read

1. On the connection's panel, under **Tables**, tick **Agents may read** beside
   each table an agent may see, or tick **Agents may read all its tables** for
   every table, including ones added later.
2. Click **Save**.

Until a table is ticked, an agent reads none of the connection.

## What happened

- `connections/<name>.yaml` holds the type and fields: `host`, `port`,
  `database`, `user`, `password: ${TRACEBI_<NAME>_PASSWORD}`, `ssl`
  ([[connections-yaml]]). A secret you typed is in
  `.tracebi/secrets.yml.enc` ([[credentials]]).
- The ticked tables are the file's `agents:` key ([[connections-yaml]]).
- The connection is on the Sources page at once, with where its data lives,
  where each credential is set, and who reads it.
- **Edit** opens the Connect step with the file's values. A saved password
  shows as `•••`; leave it empty to keep it. The file is changed in place and
  keeps its comments. **Delete…**
  removes it only when no transform, pipeline step or model reads the
  connection, and otherwise names them.

## From the command line

The same file, on the server:

```bash
tracebi connect crm --kind postgres --host db.example.com --database crm \
  --user reader --password-stdin --ssl require --store secret < password.txt
tracebi connect crm --kind postgres --url postgresql+psycopg://reader:...@db/crm --store secret
tracebi connect crm --test                       # test the saved connection
tracebi connect crm --agents accounts,clients    # or: --agents all
tracebi connect --list
```

`--password-var NAME` instead of `--password-stdin` saves nothing: the file
names `${NAME}` and the server sets it.

## Next

- Read a table in a transform: [[transform-sql]].
- Let an agent explore the tables you ticked: [[connect-chatgpt-and-claude]].
