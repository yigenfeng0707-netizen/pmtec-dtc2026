"""
PMTEC Distributed Deployment Package (P2-2).

Splits the monolithic PMTEC system into four independently deployable
gRPC microservices, each running on its own port with cross-process
communication via gRPC client connectors.

Services:
  - WarEngine        (port 50051) - simulation core, ASDA loop, EW/Cyber threats
  - BattleNetwork    (port 50052) - track feed, entity status, LVC live data
  - ApplicationStore (port 50053) - capability modules, DQN inference
  - PlugAndPlay      (port 50054) - component discovery, plugin/DT registry

Usage:
  from distributed.service_launcher import launch_all
  launch_all()  # starts all 4 services in background threads

  # Or start individually:
  from distributed.service_launcher import launch_war_engine
  launch_war_engine()  # starts only WarEngine on port 50051
"""
