@app @connect
Feature: Connect AI (MCP)
  As a candidate
  I want to connect an AI assistant to my local CV library
  So that I can search, match, and compose CVs from a chat client

  Background:
    Given the CV Studio app is running

  Scenario: Connect AI explains the integration
    When I open the "connect ai" page
    Then the response status is 200
    And the "connect" nav item is marked active
    And the page heading contains "Use your CV library"
    And the page contains "MCP"
    And the page contains "docker compose up"
    And the page contains "cv-builder"

  @wip
  Scenario: Testing the MCP connection from the UI
    # Wireframe had a connection test control; confirm against shipped connect.js.
    When I open the "connect ai" page
    Then the page contains "MCP"
