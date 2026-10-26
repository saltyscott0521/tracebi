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

1. Open **Data › Sources** and click **Add a connection**.
2. Pick the type: Postgres, MySQL, SQLite or another SQL database, DuckDB,
   Snowflake, BigQuery, a folder of CSV files, or an uploaded CSV or Parquet
   file.
3. Fill the form:
   - **Name** is how a transform reads it: `-- source: <name>.<table>`.
   - **Label** is the name people see. It is optional.
   - A password, or a URL that carries one, is masked. To keep it out of the
     app altogether, tick **Read it from an environment variable instead** and
     type `${NAME}`; set the variable on the server.
4. Click **Test**. The app opens the connection, counts its tables and closes
   it. Nothing is saved yet.
5. Click **Save**.

## Choose what agents may read

1. On the connection's panel, under **Tables**, tick **Agents may read** beside
   each table an agent may see, or tick **Agents may read all its tables** for
   every table, including ones added later.
2. Click **Save**.

Until a table is ticked, an agent reads none of the connection.

## What happened

- `connections/<name>.yaml` holds the type and fields. A secret you typed is in
  `.tracebi/secrets.yml.enc`, and the file names it as
  `${TRACEBI_<NAME>_<FIELD>}` ([[credentials]]).
- The ticked tables are the file's `agents:` key ([[connections-yaml]]).
- The connection is on the Sources page at once, with where its data lives,
  where each credential is set, and who reads it.
- **Edit** changes the file in place and keeps its comments. **Delete…**
  removes it only when no transform, pipeline step or model reads the
  connection, and otherwise names them.

## From the command line

The same file, on the server:

```bash
tracebi connect crm --kind postgres --url postgresql+psycopg://reader:...@db/crm --store secret
tracebi connect crm --agents accounts,clients    # or: --agents all
tracebi connect --list
```

## Next

- Read a table in a transform: [[transform-sql]].
- Let an agent explore the tables you ticked: [[connect-chatgpt-and-claude]].
