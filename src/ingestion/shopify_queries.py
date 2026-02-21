"""
GraphQL query definitions for Shopify Admin API (version 2026-01).

Two variants per resource:
  - PAGINATED: Used for incremental sync with cursor-based pagination.
  - BULK: Used inside bulkOperationRunQuery for full initial loads.

The bulk variants omit `first`, `after`, `pageInfo` — Shopify handles
pagination internally and returns a flat JSONL file.
"""

API_VERSION = "2026-01"

# ─── Shared fragments ────────────────────────────────────

# Money fields we need for price sets
_MONEY_FIELDS = """
    shopMoney {
      amount
      currencyCode
    }
    presentmentMoney {
      amount
      currencyCode
    }
"""

# ─── Orders ──────────────────────────────────────────────

_ORDER_FIELDS = """
    id
    name
    email
    phone
    createdAt
    updatedAt
    cancelledAt
    closedAt
    processedAt
    currencyCode
    presentmentCurrencyCode
    confirmed
    cancelReason
    tags
    note
    sourceIdentifier
    sourceName
    financialStatus: displayFinancialStatus
    fulfillmentStatus: displayFulfillmentStatus
    customerLocale
    number
    customerAcceptsMarketing
    originalTotalPriceSet { MONEY_FIELDS }
    currentSubtotalPriceSet { MONEY_FIELDS }
    currentTotalDiscountsSet { MONEY_FIELDS }
    currentTotalPriceSet { MONEY_FIELDS }
    currentTotalTaxSet { MONEY_FIELDS }
    currentShippingPriceSet { MONEY_FIELDS }
    currentTotalWeight
    estimatedTaxes
    billingAddress {
      firstName lastName company
      address1 address2 city
      province provinceCode
      country countryCodeV2
      zip phone
    }
    shippingAddress {
      firstName lastName company
      address1 address2 city
      province provinceCode
      country countryCodeV2
      zip phone
    }
    customer {
      id firstName lastName
    }
    discountCodes
    discountApplications(first: 10) {
      edges { node {
        allocationMethod
        targetSelection
        targetType
        value { ... on MoneyV2 { amount currencyCode } ... on PricingPercentageValue { percentage } }
      }}
    }
    shippingLines(first: 10) {
      edges { node {
        title code source
        discountedPriceSet { MONEY_FIELDS }
      }}
    }
    currentTaxLines {
      title rate ratePercentage
      priceSet { MONEY_FIELDS }
    }
    lineItems(first: 50) {
      edges { node {
        id
        name
        title
        variantTitle
        quantity
        sku
        vendor
        taxable
        isGiftCard
        requiresShipping
        originalUnitPriceSet { MONEY_FIELDS }
        discountedUnitPriceSet { MONEY_FIELDS }
        totalDiscountSet { MONEY_FIELDS }
        variant {
          id
          product { id }
        }
      }}
    }
    refunds(first: 10) {
      edges { node {
        id
        createdAt
        note
        refundLineItems(first: 50) {
          edges { node {
            quantity
            subtotalSet { MONEY_FIELDS }
            totalTaxSet { MONEY_FIELDS }
            restockType
            lineItem {
              id
              name
              title
              variantTitle
              sku
              vendor
              quantity
              originalUnitPriceSet { MONEY_FIELDS }
              variant {
                id
                product { id }
              }
            }
          }}
        }
        totalRefundedSet { MONEY_FIELDS }
        transactions(first: 10) {
          edges { node {
            id
            kind
            status
            gateway
            amountSet { MONEY_FIELDS }
            processedAt
          }}
        }
      }}
    }
""".replace("MONEY_FIELDS", _MONEY_FIELDS)


_ORDER_FIELDS_BULK = """
    id
    name
    email
    phone
    createdAt
    updatedAt
    cancelledAt
    closedAt
    processedAt
    currencyCode
    presentmentCurrencyCode
    confirmed
    cancelReason
    tags
    note
    sourceIdentifier
    sourceName
    financialStatus: displayFinancialStatus
    fulfillmentStatus: displayFulfillmentStatus
    customerLocale
    number
    customerAcceptsMarketing
    originalTotalPriceSet { MONEY_FIELDS }
    currentSubtotalPriceSet { MONEY_FIELDS }
    currentTotalDiscountsSet { MONEY_FIELDS }
    currentTotalPriceSet { MONEY_FIELDS }
    currentTotalTaxSet { MONEY_FIELDS }
    currentShippingPriceSet { MONEY_FIELDS }
    currentTotalWeight
    estimatedTaxes
    billingAddress {
      firstName lastName company
      address1 address2 city
      province provinceCode
      country countryCodeV2
      zip phone
    }
    shippingAddress {
      firstName lastName company
      address1 address2 city
      province provinceCode
      country countryCodeV2
      zip phone
    }
    customer {
      id firstName lastName
    }
    discountCodes
    currentTaxLines {
      title rate ratePercentage
      priceSet { MONEY_FIELDS }
    }
    lineItems {
      edges { node {
        id
        name
        title
        variantTitle
        quantity
        sku
        vendor
        taxable
        isGiftCard
        requiresShipping
        originalUnitPriceSet { MONEY_FIELDS }
        discountedUnitPriceSet { MONEY_FIELDS }
        totalDiscountSet { MONEY_FIELDS }
        variant {
          id
          product { id }
        }
      }}
    }
    refunds {
      edges { node {
        id
        createdAt
        note
        refundLineItems {
          edges { node {
            quantity
            subtotalSet { MONEY_FIELDS }
            totalTaxSet { MONEY_FIELDS }
            restockType
            lineItem {
              id
              name
              title
              variantTitle
              sku
              vendor
              quantity
              originalUnitPriceSet { MONEY_FIELDS }
              variant {
                id
                product { id }
              }
            }
          }}
        }
        totalRefundedSet { MONEY_FIELDS }
        transactions {
          edges { node {
            id
            kind
            status
            gateway
            amountSet { MONEY_FIELDS }
            processedAt
          }}
        }
      }}
    }
""".replace("MONEY_FIELDS", _MONEY_FIELDS)


ORDERS_PAGINATED = """
query OrdersSync($cursor: String, $query: String) {
  orders(first: 50, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    edges {
      node {
        ORDER_FIELDS
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".replace("ORDER_FIELDS", _ORDER_FIELDS)


ORDERS_BULK = """
{
  orders(query: "QUERY_FILTER") {
    edges {
      node {
        ORDER_FIELDS
      }
    }
  }
}
""".replace("ORDER_FIELDS", _ORDER_FIELDS_BULK)


# ─── Products ────────────────────────────────────────────

_PRODUCT_FIELDS = """
    id
    title
    descriptionHtml
    vendor
    productType
    handle
    status
    tags
    templateSuffix
    publishedAt
    createdAt
    updatedAt
    totalInventory
    options {
      id name position values
    }
    featuredMedia {
      ... on MediaImage {
        id
        image { url altText width height }
      }
    }
    media(first: 10) {
      edges { node {
        ... on MediaImage {
          id
          image { url altText width height }
        }
      }}
    }
    variants(first: 100) {
      edges { node {
        id
        title
        price
        compareAtPrice
        sku
        barcode
        position
        selectedOptions { name value }
        inventoryQuantity
        inventoryPolicy
        inventoryItem { id }
        taxable
        availableForSale
        displayName
        createdAt
        updatedAt
      }}
    }
"""

PRODUCTS_PAGINATED = """
query ProductsSync($cursor: String, $query: String) {
  products(first: 50, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    edges {
      node {
        PRODUCT_FIELDS
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".replace("PRODUCT_FIELDS", _PRODUCT_FIELDS)


PRODUCTS_BULK = """
{
  products(query: "QUERY_FILTER") {
    edges {
      node {
        PRODUCT_FIELDS
      }
    }
  }
}
""".replace("PRODUCT_FIELDS", _PRODUCT_FIELDS)


# ─── Customers ───────────────────────────────────────────

_CUSTOMER_FIELDS = """
    id
    defaultEmailAddress { emailAddress marketingState marketingOptInLevel }
    firstName
    lastName
    defaultPhoneNumber { phoneNumber marketingState marketingOptInLevel }
    state
    tags
    note
    locale
    verifiedEmail
    taxExempt
    taxExemptions
    createdAt
    updatedAt
    numberOfOrders
    amountSpent { amount currencyCode }
    lastOrder { id name }
    defaultAddress {
      id firstName lastName company
      address1 address2 city
      province provinceCode
      country countryCodeV2
      zip phone
    }
    addressesV2(first: 10) {
      edges { node {
        id firstName lastName company
        address1 address2 city
        province provinceCode
        country countryCodeV2
        zip phone
      }}
    }
"""

CUSTOMERS_PAGINATED = """
query CustomersSync($cursor: String, $query: String) {
  customers(first: 50, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    edges {
      node {
        CUSTOMER_FIELDS
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
""".replace("CUSTOMER_FIELDS", _CUSTOMER_FIELDS)


CUSTOMERS_BULK = """
{
  customers(query: "QUERY_FILTER") {
    edges {
      node {
        CUSTOMER_FIELDS
      }
    }
  }
}
""".replace("CUSTOMER_FIELDS", _CUSTOMER_FIELDS)


# ─── Bulk operation mutations ────────────────────────────

BULK_OPERATION_RUN = """
mutation BulkOperationRun($query: String!) {
  bulkOperationRunQuery(query: $query) {
    bulkOperation {
      id
      status
    }
    userErrors {
      field
      message
    }
  }
}
"""

BULK_OPERATION_POLL = """
query BulkOperationPoll($id: ID!) {
  node(id: $id) {
    ... on BulkOperation {
      id
      status
      errorCode
      objectCount
      fileSize
      url
      partialDataUrl
      createdAt
      completedAt
    }
  }
}
"""

BULK_OPERATION_CANCEL = """
mutation BulkOperationCancel($id: ID!) {
  bulkOperationCancel(id: $id) {
    bulkOperation {
      id
      status
    }
    userErrors {
      field
      message
    }
  }
}
"""
