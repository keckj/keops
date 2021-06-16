
#include <vector>
#include <string>

#include "Sizes.h"

class Ranges {
public:
  int tagRanges, nranges_x, nranges_y, nredranges_x, nredranges_y;
  
  std::vector< __INDEX__* > _castedranges;
  std::vector< __INDEX__ > ranges_i, slices_i, redranges_j;
  __INDEX__** castedranges;
  
  Ranges(Sizes sizes, int nranges, index_t* ranges) {
    
    // Sparsity: should we handle ranges? ======================================
    if (sizes.nbatchdims == 0) {  // Standard M-by-N computation
      if (nranges == 0) {
        
        tagRanges = 0;
        
        nranges_x = 0;
        nranges_y = 0;
        
        nredranges_x = 0;
        nredranges_y = 0;
        
      } else if (nranges == 6) {
  
        tagRanges = 1;
        nranges_x = get_size(ranges[0], 0);
        nranges_y = get_size(ranges[3], 0);
        
        nredranges_x = get_size(ranges[5], 0);
        nredranges_y = get_size(ranges[2], 0);
        
        // get the pointers to data to avoid a copy
        _castedranges.resize(nranges);
        for (int i = 0; i < nranges; i++)
          _castedranges[i] = ranges[i];
        
        castedranges = &_castedranges[0];
      }
      
    } else if (nranges == 0) {
      // Batch processing: we'll have to generate a custom, block-diagonal sparsity pattern
      tagRanges = 1;  // Batch processing is emulated through the block-sparse mode
      
      // Create new "castedranges" from scratch ------------------------------
      // With pythonic notations, we'll have:
      //   castedranges = (ranges_i, slices_i, redranges_j,   ranges_j, slices_j, redranges_i)
      // with:
      // - ranges_i    = redranges_i = [ [0,M], [M,2M], ..., [(nbatches-1)M, nbatches*M] ]
      // - slices_i    = slices_j    = [    1,     2,   ...,   nbatches-1,   nbatches    ]
      // - redranges_j = ranges_j    = [ [0,N], [N,2N], ..., [(nbatches-1)N, nbatches*N] ]
      
      //__INDEX__* castedranges[6];
      _castedranges.resize(6);
      
      //__INDEX__ ranges_i[2 * sizes.nbatches];  // ranges_i
      ranges_i.resize(2 * sizes.nbatches, 0);
      
      //__INDEX__ slices_i[sizes.nbatches];    // slices_i
      slices_i.resize(sizes.nbatches, 0);
      
      //__INDEX__ redranges_j[2 * sizes.nbatches];  // redranges_j
      redranges_j.resize(2 * sizes.nbatches, 0);
      
      for (int b = 0; b < sizes.nbatches; b++) {
        ranges_i[2 * b] = b * sizes.M;
        ranges_i[2 * b + 1] = (b + 1) * sizes.M;
        slices_i[b] = (b + 1);
        redranges_j[2 * b] = b * sizes.N;
        redranges_j[2 * b + 1] = (b + 1) * sizes.N;
      }
  
      _castedranges[0] = &ranges_i[0];
      _castedranges[1] = &slices_i[0];
      _castedranges[2] = &redranges_j[0];
      _castedranges[3] = &redranges_j[0];            // ranges_j
      _castedranges[4] = &slices_i[0];            // slices_j
      _castedranges[5] = &ranges_i[0];            // redranges_i
 
      
      nranges_x = sizes.nbatches;
      nredranges_x = sizes.nbatches;
      nranges_y = sizes.nbatches;
      nredranges_y = sizes.nbatches;
      castedranges = &_castedranges[0];
  
    } else {
      throw std::runtime_error(
              "[KeOps] The 'ranges' argument (block-sparse mode) is not supported with batch processing, "
              "but we detected " + std::to_string(sizes.nbatchdims) + " > 0 batch dimensions."
      );
    }
  

    
  };
  
};