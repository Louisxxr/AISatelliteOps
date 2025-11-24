from neo4j import GraphDatabase


uri = "bolt://localhost:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "1234abcd"))

with driver.session() as session:
    # result = session.run("MATCH (n:Person) RETURN n.name AS name")
    result = session.run("MATCH (n) RETURN n")
    for record in result:
        print(record.data())