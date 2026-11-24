"""GraphQL queries sent to Madlan's API (``https://www.madlan.co.il/api2``).

Contact fields (``poc``, ``agent``, ``userPhoneNumberEdit``) are never requested.
"""

BULLETIN_FIELDS = """
id dealType price beds area floor floors ppm address firstTimeSeen lastUpdated
generalCondition buildingYear description monthlyTaxes commonCharges availableDate
addressDetails { city neighbourhood streetName streetNumber cityDocId neighbourhoodDocId }
locationPoint { lat lng }
images { imageUrl isFloorplan }
eventsHistory { eventType date price }
amenities {
  accessible airConditioner balcony basement doorman elevator furnished garage garden gym heating
  parking pool roofDeck secureRoom storage sunBoiler terrace unitPetsAllowed
}
"""

SEARCH = f"""
query searchPoi(
  $dealType: String, $locationDocId: String, $limit: Int, $offset: Int, $sort: [SortField],
  $priceRange: [Int], $roomsRange: [Float], $areaRange: [Int], $floorRange: [Int],
  $sellerType: [SellerType], $generalCondition: [GeneralCondition], $amenities: inputAmenitiesFilter,
  $priceDrop: Boolean, $creationDaysRange: Int, $onlyImmediate: Boolean, $noFee: Boolean
) {{
  searchPoiV2(
    dealType: $dealType, locationDocId: $locationDocId, poiTypes: [bulletin], limit: $limit,
    offset: $offset, sort: $sort, priceRange: $priceRange, roomsRange: $roomsRange,
    areaRange: $areaRange, floorRange: $floorRange, sellerType: $sellerType,
    generalCondition: $generalCondition, amenities: $amenities, priceDrop: $priceDrop,
    creationDaysRange: $creationDaysRange, onlyImmediate: $onlyImmediate, noFee: $noFee
  ) {{
    total
    cursor {{ bulletinsOffset }}
    poi {{ id type ... on Bulletin {{ {BULLETIN_FIELDS} }} }}
  }}
}}
"""

BY_IDS = f"""
query poiByIds($ids: [PoiIds!]) {{
  poiByIds(ids: $ids) {{ id type ... on Bulletin {{ {BULLETIN_FIELDS} }} }}
}}
"""

LOCATIONS = """
query addresses($text: String!, $completionTypes: [String]) {
  addresses(text: $text, completionTypes: $completionTypes) { docId name type city }
}
"""
