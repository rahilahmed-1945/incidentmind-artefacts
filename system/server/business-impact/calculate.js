// Business Impact Calculator V2 - Realistic INR Edition
// Fully deterministic math and formula-based impact evaluation.

const serviceMetadata = {
  'gateway-service': { userWeight: 0.8, revenueWeight: 0.8 },
  'auth-service': { userWeight: 0.8, revenueWeight: 0.8 },
  'checkout-service': { userWeight: 0.6, revenueWeight: 0.9 },
  'payments-service': { userWeight: 0.4, revenueWeight: 1.0 },
  'inventory-service': { userWeight: 0.3, revenueWeight: 0.4 },
  'redis-cache': { userWeight: 0.5, revenueWeight: 0.5 },
  'primary-db': { userWeight: 0.9, revenueWeight: 0.9 },
  'user-profile-service': { userWeight: 0.2, revenueWeight: 0.0 }
};

const companyMetadata = {
  dailyActiveUsers: 120000,
  transactionsPerMinute: 45,
  averageOrderValueINR: 850,
  monthlyRevenueINR: 15000000, // 1.5 Crore
  slaTarget: 99.9
};

function formatINR(number) {
  if (number >= 10000000) {
    return `₹${(number / 10000000).toFixed(2)} Crore`;
  } else if (number >= 100000) {
    return `₹${(number / 100000).toFixed(2)} Lakh`;
  }
  return `₹${number.toLocaleString('en-IN')}`;
}

function calculateBusinessImpact(blastRadius, incidentTimeline) {
  // Extract outage duration in minutes from timeline
  let outageDurationMins = 0;
  if (incidentTimeline && incidentTimeline.length > 0) {
    const start = new Date(incidentTimeline[0].timestamp).getTime();
    const end = new Date(incidentTimeline[incidentTimeline.length - 1].timestamp).getTime();
    outageDurationMins = Math.max(1, Math.round((end - start) / 60000));
  }

  const allImpacted = new Set([
    blastRadius.rootService,
    ...(blastRadius.directlyImpacted || []),
    ...(blastRadius.indirectlyImpacted || [])
  ]);

  // 1. Calculate cumulative weights
  let cumulativeUserImpact = 0.0;
  let cumulativeRevenueImpact = 0.0;

  allImpacted.forEach(srv => {
    if (serviceMetadata[srv]) {
      cumulativeUserImpact += serviceMetadata[srv].userWeight;
      cumulativeRevenueImpact += serviceMetadata[srv].revenueWeight;
    }
  });

  // Cap at 1.0 (100%)
  const userImpactRatio = Math.min(1.0, cumulativeUserImpact);
  const revenueImpactRatio = Math.min(1.0, cumulativeRevenueImpact);

  // 2. Perform Calculations (V2 Realistic Logic)
  const dailyRevenue = companyMetadata.monthlyRevenueINR / 30;
  const hourlyRevenue = dailyRevenue / 24;
  const revenueRiskPerHour = hourlyRevenue * revenueImpactRatio;
  
  const affectedUsers = Math.round(companyMetadata.dailyActiveUsers * userImpactRatio);
  
  const transactionsImpacted = Math.round(companyMetadata.transactionsPerMinute * revenueImpactRatio * outageDurationMins);
  
  const checkoutMultiplier = (allImpacted.has('checkout-service') || allImpacted.has('payments-service')) ? 1.0 : (revenueImpactRatio * 0.5);
  const ordersImpacted = Math.round(transactionsImpacted * checkoutMultiplier);
  
  const estimatedDowntimeCost = Math.round((revenueRiskPerHour / 60) * outageDurationMins);

  // 3. Categorizations
  let slaRisk = "Low";
  if (outageDurationMins > 43) slaRisk = "Critical"; // 43 mins is typical monthly budget for 99.9%
  else if (outageDurationMins > 20 && revenueImpactRatio > 0.5) slaRisk = "High";
  else if (outageDurationMins > 10) slaRisk = "Medium";

  // Rebalanced Severity Thresholds for Mid-Sized INR Company
  let businessSeverity = "SEV-4";
  if (revenueRiskPerHour > 50000 || affectedUsers > 50000) businessSeverity = "SEV-1";
  else if (revenueRiskPerHour > 20000) businessSeverity = "SEV-2";
  else if (revenueRiskPerHour > 5000) businessSeverity = "SEV-3";

  let customerImpact = "Low";
  if (userImpactRatio >= 0.8) customerImpact = "Severe";
  else if (userImpactRatio >= 0.5) customerImpact = "High";
  else if (userImpactRatio >= 0.2) customerImpact = "Medium";

  // 4. Formula Breakdown Traceability
  const formulaBreakdown = {
    revenueRisk: `HourlyRevenue (₹${Math.round(hourlyRevenue).toLocaleString('en-IN')}) * RevenueImpact (${revenueImpactRatio.toFixed(2)}) = ₹${Math.round(revenueRiskPerHour).toLocaleString('en-IN')}/hr`,
    affectedUsers: `DAU (${companyMetadata.dailyActiveUsers.toLocaleString('en-IN')}) * UserImpact (${userImpactRatio.toFixed(2)}) = ${affectedUsers.toLocaleString('en-IN')}`,
    transactionsImpacted: `TPM (${companyMetadata.transactionsPerMinute}) * RevenueImpact (${revenueImpactRatio.toFixed(2)}) * Duration (${outageDurationMins}m) = ${transactionsImpacted.toLocaleString('en-IN')}`,
    ordersImpacted: `TransactionsImpacted (${transactionsImpacted.toLocaleString('en-IN')}) * CheckoutMultiplier (${checkoutMultiplier.toFixed(2)}) = ${ordersImpacted.toLocaleString('en-IN')}`,
    downtimeCost: `(RevenueRiskPerHour (₹${Math.round(revenueRiskPerHour).toLocaleString('en-IN')}) / 60) * Duration (${outageDurationMins}m) = ₹${estimatedDowntimeCost.toLocaleString('en-IN')}`
  };

  return {
    affectedUsers,
    revenueRiskPerHour: Math.round(revenueRiskPerHour),
    transactionsImpacted,
    ordersImpacted,
    estimatedDowntimeCost,
    slaRisk,
    businessSeverity,
    customerImpact,
    formulaBreakdown,
    formatted: {
      revenueRiskPerHour: formatINR(Math.round(revenueRiskPerHour)),
      estimatedDowntimeCost: formatINR(estimatedDowntimeCost),
      affectedUsers: affectedUsers.toLocaleString('en-IN'),
      transactionsImpacted: transactionsImpacted.toLocaleString('en-IN'),
      ordersImpacted: ordersImpacted.toLocaleString('en-IN')
    }
  };
}

module.exports = { calculateBusinessImpact, companyMetadata, formatINR };
