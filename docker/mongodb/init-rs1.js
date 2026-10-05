db = db.getSiblingDB("admin");
rs.initiate({
  _id: "rs1",
  version: 1,
  members: [
    { _id: 0, host: "mongo-rs1:27017", priority: 2 },
    { _id: 1, host: "mongo-rs0:27017", priority: 1 },
    { _id: 2, host: "mongo-rs2:27017", priority: 0, hidden: true, votes: 0 }
  ]
});
