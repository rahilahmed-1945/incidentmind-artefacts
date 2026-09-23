const { retrieveKeyword } = require('./retrieve-keyword'); // Corrected import based on test-semantic.js usage if needed, wait, the original index.js exported retrieve as retrieveKeyword.
const { retrieveSemantic } = require('./retrieve-semantic');
const { retrieveSemanticV2 } = require('./retrieve-semantic-v2');
const { retrieveRootCause } = require('./retrieve-rootcause');
const { ingest } = require('./embed');

module.exports = {
  retrieveKeyword: require('./retrieve-keyword').retrieve,
  retrieveSemantic,
  retrieveSemanticV2,
  retrieveRootCause,
  ingest
};
